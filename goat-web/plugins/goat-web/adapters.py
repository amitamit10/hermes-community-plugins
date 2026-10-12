"""Dependency-free adapter spikes for readable text, crawling, and RSS.

The crawl helper never opens a socket: callers inject a transport callable
matching goat_tools' ``transport(url)`` convention. Keep network access and URL
safety in that injected transport.
"""

from collections import deque
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit
import re
import xml.etree.ElementTree as ET


MAX_CRAWL_DEPTH = 2
MAX_CRAWL_PAGES = 10

# Fixed offline fixture for the deliberately small RSS parsing spike.
SAMPLE_RSS_FEED = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <title>Example feed</title>
    <link>https://example.com/</link>
    <description>Offline adapter fixture</description>
    <item>
      <title>Sample article</title>
      <link>https://example.com/articles/sample</link>
      <description>A short sample summary.</description>
      <pubDate>Fri, 09 Oct 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


_IGNORED_TAGS = frozenset(
    ("aside", "button", "footer", "form", "head", "header", "nav", "noscript", "script", "style", "svg", "template")
)
_VOID_TAGS = frozenset(
    ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr")
)
_BLOCK_TAGS = frozenset(
    ("address", "article", "blockquote", "br", "div", "dl", "fieldset", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "li", "main", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul")
)


_BOILERPLATE_ATTR_RE = re.compile(
    r"cookie|consent|gdpr|promo|newsletter|subscribe|subscription|related|"
    r"recommend|sidebar|menu|banner|advert|sponsor|popup|signup|sign-?up|"
    r"social|share|comment|author-?bio",
    re.IGNORECASE,
)

_HIGH_CONTENT_TAGS = frozenset(
    ("article", "main", "p", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote")
)
_MAIN_ANCESTOR_TAGS = frozenset(("article", "main"))


def _score_segment(text, tag, ancestor_tags, attr_text, link_ratio):
    """Score one block segment; positive means likely main content."""
    if tag in ("article", "main"):
        base = 4
    elif tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"):
        base = 3
    elif tag is None:
        base = 1
    else:
        base = 0
    try:
        ancestors = set(ancestor_tags) if ancestor_tags else set()
    except Exception:
        ancestors = set()
    if ancestors & _MAIN_ANCESTOR_TAGS:
        base += 2
    length = len(text) if isinstance(text, str) else 0
    if length >= 100:
        base += 2
    elif length >= 20:
        base += 1
    try:
        boilerplate = bool(attr_text and _BOILERPLATE_ATTR_RE.search(attr_text))
    except Exception:
        boilerplate = False
    if boilerplate:
        base -= 6
    try:
        ratio = float(link_ratio) if link_ratio else 0.0
    except Exception:
        ratio = 0.0
    if ratio < 0.0:
        ratio = 0.0
    if ratio > 1.0:
        ratio = 1.0
    base -= 3.0 * ratio
    return base


class _ReadableTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._ignored_stack = []
        self._stack = []
        self._root_chunks = []
        self._root_link_chars = 0
        self._anchor_depth = 0
        self._segments = []
        self._order = 0
        self._seq = 0
        self._root_first_seq = None

    def _current_frame(self):
        return self._stack[-1] if self._stack else None

    def _finalize_frame(self, frame):
        raw = "".join(frame.get("chunks") or [])
        text = re.sub(r"\s+", " ", raw).strip()
        if not text:
            return
        denom = len(raw.strip())
        if denom <= 0:
            denom = len(text)
        if denom <= 0:
            denom = 1
        link_chars = frame.get("link_chars") or 0
        ratio = link_chars / float(denom)
        if ratio > 1.0:
            ratio = 1.0
        own_attr = ((frame.get("class") or "") + " " + (frame.get("id") or ""))
        ancestor_attr = frame.get("ancestor_attr") or ""
        score = _score_segment(
            text,
            frame.get("tag"),
            frame.get("ancestors") or (),
            (own_attr + " " + ancestor_attr),
            ratio,
        )
        self._segments.append(
            {"order": frame.get("first_seq", frame.get("order", 0)), "text": text, "score": score}
        )

    def handle_starttag(self, tag, attrs):
        lowered = tag.lower()
        if self._ignored_stack:
            if lowered not in _VOID_TAGS:
                self._ignored_stack.append(lowered)
            return
        if lowered in _IGNORED_TAGS:
            if lowered not in _VOID_TAGS:
                self._ignored_stack.append(lowered)
            return
        if lowered == "a":
            self._anchor_depth += 1
            return
        if lowered in _VOID_TAGS:
            piece = " "
            frame = self._current_frame()
            if frame is not None:
                frame["chunks"].append(piece)
            else:
                self._root_chunks.append(piece)
            return
        if lowered in _BLOCK_TAGS:
            try:
                mapping = dict(attrs)
            except Exception:
                mapping = {}
            cls = mapping.get("class") or ""
            iid = mapping.get("id") or ""
            if not isinstance(cls, str):
                cls = str(cls)
            if not isinstance(iid, str):
                iid = str(iid)
            ancestor_attr = " ".join(
                ((fr.get("class") or "") + " " + (fr.get("id") or ""))
                for fr in self._stack
            )
            frame = {
                "tag": lowered,
                "class": cls,
                "id": iid,
                "chunks": [],
                "link_chars": 0,
                "order": self._order,
                "first_seq": None,
                "ancestors": [fr.get("tag") for fr in self._stack],
                "ancestor_attr": ancestor_attr,
            }
            self._order += 1
            self._stack.append(frame)
            return
        return

    def handle_endtag(self, tag):
        lowered = tag.lower()
        if self._ignored_stack:
            if lowered in self._ignored_stack:
                index = len(self._ignored_stack) - 1 - self._ignored_stack[::-1].index(lowered)
                del self._ignored_stack[index:]
            return
        if lowered == "a":
            if self._anchor_depth > 0:
                self._anchor_depth -= 1
            return
        if lowered in _VOID_TAGS:
            return
        if lowered in _BLOCK_TAGS:
            for pos in range(len(self._stack) - 1, -1, -1):
                if self._stack[pos].get("tag") == lowered:
                    pending = self._stack[pos:]
                    del self._stack[pos:]
                    for frame in reversed(pending):
                        self._finalize_frame(frame)
                    break
            return

    def handle_startendtag(self, tag, attrs):
        lowered = tag.lower()
        if self._ignored_stack:
            return
        if lowered in _IGNORED_TAGS:
            return
        if lowered == "a":
            return
        if lowered in _BLOCK_TAGS and lowered in _VOID_TAGS:
            frame = self._current_frame()
            if frame is not None:
                frame["chunks"].append(" ")
            else:
                self._root_chunks.append(" ")
            return
        if lowered in _BLOCK_TAGS:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)
            return

    def handle_data(self, data):
        if self._ignored_stack:
            return
        if not data:
            return
        self._seq += 1
        frame = self._current_frame()
        if frame is not None:
            if frame.get("first_seq") is None:
                frame["first_seq"] = self._seq
            frame["chunks"].append(data)
            if self._anchor_depth > 0:
                try:
                    frame["link_chars"] += len(data)
                except Exception:
                    pass
        else:
            if self._root_first_seq is None:
                self._root_first_seq = self._seq
            self._root_chunks.append(data)
            if self._anchor_depth > 0:
                try:
                    self._root_link_chars += len(data)
                except Exception:
                    pass

    def close(self):
        try:
            super().close()
        finally:
            for frame in reversed(list(self._stack)):
                try:
                    self._finalize_frame(frame)
                except Exception:
                    pass
            self._stack = []

    def scored_segments(self):
        out = list(self._segments)
        raw_root = "".join(self._root_chunks)
        root_text = re.sub(r"\s+", " ", raw_root).strip()
        if root_text:
            denom = len(raw_root.strip()) or len(root_text) or 1
            ratio = (self._root_link_chars / float(denom)) if denom else 0.0
            if ratio > 1.0:
                ratio = 1.0
            score = _score_segment(root_text, None, (), "", ratio)
            order = self._root_first_seq if self._root_first_seq is not None else 10**9
            out.append({"order": order, "text": root_text, "score": score})
        out.sort(key=lambda item: item["order"])
        return out


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def trafilatura_like_extract(html):
    """Return whitespace-normalized readable text from basic HTML markup.

    PLACEHOLDER ONLY: this small stdlib parser is not Trafilatura and does not
    reproduce its extraction quality. Replace it with the real ``trafilatura``
    dependency (Apache-2.0) when that dependency is approved for integration.
    """
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    if not isinstance(html, str):
        raise TypeError("html must be str or bytes")
    parser = _ReadableTextParser()
    parser.feed(html)
    parser.close()
    segments = parser.scored_segments()
    if not segments:
        return ""
    has_positive = any(item["score"] > 0 for item in segments)
    if has_positive:
        kept = [item["text"] for item in segments if item["score"] > 0]
        if not kept:
            kept = [item["text"] for item in segments]
    else:
        kept = [item["text"] for item in segments]
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def _origin(url):
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("URL must be absolute HTTP(S)")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed")
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL has an invalid port") from error
    return scheme, host, port or (443 if scheme == "https" else 80)


def _same_origin(url, expected_origin):
    try:
        return _origin(url) == expected_origin
    except (UnicodeError, ValueError):
        return False


def _bounded(value, default, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        parsed = default
    return min(max(0, parsed), maximum)


def _response_parts(response):
    """Read the same simple response shapes accepted by goat_tools."""
    if isinstance(response, (str, bytes)):
        status, body, final_url = 200, response, None
    elif isinstance(response, dict):
        status = response.get("status", 200)
        body = response.get("body", response.get("text", ""))
        final_url = response.get("url", response.get("final_url"))
    else:
        status = getattr(response, "status", 200)
        body = getattr(response, "body", getattr(response, "text", ""))
        final_url = getattr(response, "url", getattr(response, "final_url", None))
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    elif not isinstance(body, str):
        body = str(body) if body is not None else ""
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    return status, body, final_url


def crawl_frontier(start_url, transport, *, max_depth=MAX_CRAWL_DEPTH, max_pages=MAX_CRAWL_PAGES):
    """Breadth-first crawl with a seen set, same-origin filter, and hard bounds.

    ``transport`` must be an injected callable taking one URL and returning a
    goat_tools-style response (text/bytes or a mapping with status/body/url).
    Requested limits are clamped to depth 2 and 10 pages. The returned mapping
    contains page mappings with ``url``, ``depth``, ``status``, and ``content``.
    """
    if not callable(transport):
        raise TypeError("transport must be callable")
    origin = _origin(start_url)
    start_url = urldefrag(start_url)[0]
    depth_limit = _bounded(max_depth, MAX_CRAWL_DEPTH, MAX_CRAWL_DEPTH)
    page_limit = _bounded(max_pages, MAX_CRAWL_PAGES, MAX_CRAWL_PAGES)

    frontier = deque(((start_url, 0),))
    seen = {start_url}
    pages = []
    truncated = False

    while frontier and len(pages) < page_limit:
        current, depth = frontier.popleft()
        if not _same_origin(current, origin):
            continue
        response = transport(current)
        status, body, final_url = _response_parts(response)
        final_url = final_url or current
        if not _same_origin(final_url, origin):
            raise ValueError("transport returned a cross-origin final URL")
        final_url = urldefrag(final_url)[0]
        pages.append({"url": current, "depth": depth, "status": status, "content": body})

        parser = _LinkParser()
        parser.feed(body)
        parser.close()
        for href in parser.links:
            target = urldefrag(urljoin(final_url, href))[0]
            if target in seen or not _same_origin(target, origin):
                continue
            seen.add(target)
            if depth >= depth_limit:
                truncated = True
            else:
                frontier.append((target, depth + 1))

    if frontier:
        truncated = True
    return {"ok": True, "pages": pages, "truncated": truncated}


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element, names):
    for child in element:
        if _local_name(child.tag) in names:
            return " ".join("".join(child.itertext()).split())
    return ""


def rss_parse(feed_xml=SAMPLE_RSS_FEED):
    """Parse a small RSS 2.0 feed into title/url/summary/published mappings.

    This is a dependency-free fixture adapter, not a complete RSS or Atom
    implementation. ``feed_xml`` defaults to the fixed offline sample feed.
    """
    if isinstance(feed_xml, bytes):
        feed_xml = feed_xml.decode("utf-8", errors="replace")
    if not isinstance(feed_xml, str):
        raise TypeError("feed_xml must be str or bytes")
    root = ET.fromstring(feed_xml)
    channel = root if _local_name(root.tag) == "channel" else next(
        (child for child in root if _local_name(child.tag) == "channel"), None
    )
    if channel is None:
        return []

    items = []
    for element in channel:
        if _local_name(element.tag) != "item":
            continue
        items.append(
            {
                "title": _child_text(element, {"title"}),
                "url": _child_text(element, {"link"}),
                "summary": _child_text(element, {"description", "summary"}),
                "published": _child_text(element, {"pubdate", "published"}),
            }
        )
    return items
