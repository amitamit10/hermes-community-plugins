"""Small stdlib RSS/Atom watcher with an injected fetcher and watermark dedup.

No network access is performed by this module. ``fetcher(url)`` must be
provided by the caller and may return XML text/bytes, a mapping with ``body``
(or ``text``) and optional ``status``, or an object with equivalent attrs.
"""

from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from ssrf_guard import MAX_RESPONSE_BYTES


_DEFAULT_MAX_ITEMS = 20
_DEFAULT_MAX_SEEN = 500
_STATE_VERSION = 1
MAX_FEED_BYTES = MAX_RESPONSE_BYTES


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element, names):
    for child in element:
        if _local_name(child.tag) in names:
            return " ".join("".join(child.itertext()).split())
    return ""


def _item_link(element):
    for child in element:
        if _local_name(child.tag) != "link":
            continue
        text = " ".join("".join(child.itertext()).split())
        if text:
            return text
        href = child.attrib.get("href", "")
        if href:
            return href.strip()
    return ""


def _bounded_feed_text(feed_xml):
    if isinstance(feed_xml, bytes):
        if len(feed_xml) > MAX_FEED_BYTES:
            raise ValueError("feed exceeds byte limit")
        return feed_xml.decode("utf-8", errors="replace")
    if not isinstance(feed_xml, str):
        raise TypeError("feed_xml must be str or bytes")
    used = 0
    for char in feed_xml:
        used += len(char.encode("utf-8", errors="replace"))
        if used > MAX_FEED_BYTES:
            raise ValueError("feed exceeds byte limit")
    return feed_xml


def parse_feed(feed_xml):
    """Parse RSS 2.0 or Atom XML into ordered item mappings.

    Each mapping has ``id``, ``title``, ``url``, ``summary``, and
    ``published`` fields. IDs prefer RSS ``guid`` / Atom ``id``, then link,
    then a deterministic content hash when the feed provides neither.
    """
    feed_xml = _bounded_feed_text(feed_xml)
    root = ET.fromstring(feed_xml)
    root_name = _local_name(root.tag)
    if root_name == "channel":
        container = root
        item_name = "item"
    elif root_name == "feed":
        container = root
        item_name = "entry"
    else:
        container = next(
            (child for child in root if _local_name(child.tag) == "channel"),
            None,
        )
        item_name = "item"
        if container is None:
            return []

    items = []
    for element in container:
        if _local_name(element.tag) != item_name:
            continue
        title = _child_text(element, {"title"})
        url = _item_link(element)
        summary = _child_text(element, {"description", "summary", "content"})
        published = _child_text(element, {"pubdate", "published", "updated", "date"})
        item_id = _child_text(element, {"guid", "id"}) or url
        if not item_id:
            stable_fields = "\0".join((title, published, summary))
            item_id = "sha256:" + hashlib.sha256(stable_fields.encode("utf-8")).hexdigest()
        items.append(
            {
                "id": item_id,
                "title": title,
                "url": url,
                "summary": summary,
                "published": published,
            }
        )
    return items


def _response_parts(response):
    if isinstance(response, (str, bytes)):
        status, body = 200, response
    elif isinstance(response, dict):
        status = response.get("status", 200)
        body = response.get("body", response.get("text", ""))
    else:
        status = getattr(response, "status", 200)
        body = getattr(response, "body", getattr(response, "text", ""))
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    if body is None:
        body = ""
    body = _bounded_feed_text(body)
    return status, body


class RSSWatcher:
    """Poll a feed and return only unseen items, up to ``max_items`` per poll.

    The fetcher is injected so callers control all network access. IDs for
    returned items are stored in a bounded watermark. Supplying ``state_path``
    persists that watermark as JSON across watcher instances; otherwise the
    watermark lives for this instance only. Items beyond the per-poll limit
    remain unseen and can be returned on a subsequent poll.
    """

    def __init__(self, fetcher, *, max_items=_DEFAULT_MAX_ITEMS,
                 state_path=None, max_seen=_DEFAULT_MAX_SEEN):
        if not callable(fetcher):
            raise TypeError("fetcher must be callable")
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 0:
            raise ValueError("max_items must be a non-negative integer")
        if isinstance(max_seen, bool) or not isinstance(max_seen, int) or max_seen < 1:
            raise ValueError("max_seen must be a positive integer")
        self._fetcher = fetcher
        self.max_items = max_items
        self.max_seen = max_seen
        self._state_path = Path(state_path) if state_path is not None else None
        self._seen = OrderedDict()
        if self._state_path is not None:
            self._load_state()

    @property
    def seen_ids(self):
        """Return the current watermark as an immutable oldest-to-newest tuple."""
        return tuple(self._seen)

    def poll(self, feed_url):
        """Fetch one feed and return its unseen entries, oldest feed order first."""
        if not isinstance(feed_url, str) or not feed_url.strip():
            raise ValueError("feed_url must be a non-empty string")
        status, body = _response_parts(self._fetcher(feed_url))
        if not 200 <= status < 300:
            raise RuntimeError(f"feed fetch failed with HTTP status {status}")
        parsed_items = parse_feed(body)
        unseen = [item for item in parsed_items if item["id"] not in self._seen]
        selected = unseen[:self.max_items]
        if selected:
            for item in selected:
                self._remember(item["id"])
            self._save_state()
        return selected

    def _remember(self, item_id):
        self._seen[item_id] = None
        self._seen.move_to_end(item_id)
        while len(self._seen) > self.max_seen:
            self._seen.popitem(last=False)

    def _load_state(self):
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"could not read watermark state: {error}") from error
        if not isinstance(payload, dict) or payload.get("version") != _STATE_VERSION:
            raise ValueError("unsupported watermark state format")
        ids = payload.get("seen")
        if not isinstance(ids, list) or any(not isinstance(item_id, str) or not item_id for item_id in ids):
            raise ValueError("watermark state must contain a list of non-empty IDs")
        for item_id in ids:
            self._remember(item_id)

    def _save_state(self):
        if self._state_path is None:
            return
        parent = self._state_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _STATE_VERSION, "seen": list(self._seen)}
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=parent,
                prefix=f".{self._state_path.name}.", suffix=".tmp", delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(payload, temporary, ensure_ascii=False, separators=(",", ":"))
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self._state_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
