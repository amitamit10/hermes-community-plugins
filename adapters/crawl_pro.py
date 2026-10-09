"""Bounded, injected-transport crawler with sitemap and robots support.

All requests are made serially through the caller-supplied ``transport(url)``.
The result includes a per-host request counter (including robots and sitemap
requests) so callers can account for crawler politeness without hidden I/O.
"""

from collections import deque
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET


MAX_CRAWL_DEPTH = 3
MAX_CRAWL_PAGES = 25
MAX_SITEMAP_DOCUMENTS = 8
MAX_SITEMAP_URLS = 250


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


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


def _clean_url(url):
    return urldefrag(url.strip())[0]


def _bounded(value, default, lower, upper):
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        parsed = default
    return min(max(parsed, lower), upper)


def _response_parts(response):
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


def _request(url, transport, expected_origin, requests_by_host):
    if not _same_origin(url, expected_origin):
        raise ValueError("crawler request is outside the starting origin")
    host = expected_origin[1]
    requests_by_host[host] = requests_by_host.get(host, 0) + 1
    status, body, final_url = _response_parts(transport(url))
    final_url = _clean_url(final_url or url)
    if not _same_origin(final_url, expected_origin):
        raise ValueError("transport returned a cross-origin final URL")
    return status, body, final_url


def _root_path_url(url, expected_origin, path):
    scheme, host, port = expected_origin
    host_part = f"[{host}]" if ":" in host else host
    default_port = 443 if scheme == "https" else 80
    netloc = host_part if port == default_port else f"{host_part}:{port}"
    return urlunsplit((scheme, netloc, path, "", ""))


def _parse_robots_disallows(body):
    """Parse only Disallow rules in the wildcard user-agent group."""
    rules = []
    agents = []
    group_has_directive = False

    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = line.split(":", 1)
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if group_has_directive:
                agents = []
                group_has_directive = False
            if value:
                agents.append(value.lower())
            continue
        if not agents:
            continue
        group_has_directive = True
        if field == "disallow" and "*" in agents and value.startswith("/"):
            rules.append(value)
    return tuple(dict.fromkeys(rules))


def _load_robots(url, transport, origin, requests_by_host):
    robots_url = _root_path_url(url, origin, "/robots.txt")
    try:
        status, body, _final_url = _request(robots_url, transport, origin, requests_by_host)
    except Exception:
        # If the policy file cannot be read, fail closed rather than ignoring it.
        return ("/",)
    if 200 <= status < 300:
        return _parse_robots_disallows(body)
    if status in (404, 410):
        return ()
    return ("/",)


def _is_disallowed(url, rules):
    if not rules:
        return False
    path = urlsplit(url).path or "/"
    return any(path.startswith(rule) for rule in rules)


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _entry_loc(entry):
    for element in entry.iter():
        if _local_name(element.tag) == "loc" and element.text:
            return element.text.strip()
    return ""


def _parse_sitemap(body):
    """Return (page URLs, child sitemap URLs) from a sitemap XML document."""
    try:
        root = ET.fromstring(body)
    except (ET.ParseError, ValueError):
        return [], []
    kind = _local_name(root.tag)
    if kind == "urlset":
        return [_entry_loc(entry) for entry in root if _local_name(entry.tag) == "url"], []
    if kind == "sitemapindex":
        return [], [_entry_loc(entry) for entry in root if _local_name(entry.tag) == "sitemap"]
    return [], []


def _sitemap_urls(start_url, transport, origin, requests_by_host, robots_rules):
    first = _root_path_url(start_url, origin, "/sitemap.xml")
    pending = deque((first,))
    seen_sitemaps = set()
    seen_pages = set()
    pages = []

    while pending and len(seen_sitemaps) < MAX_SITEMAP_DOCUMENTS and len(pages) < MAX_SITEMAP_URLS:
        sitemap_url = _clean_url(urljoin(first, pending.popleft()))
        if sitemap_url in seen_sitemaps or not _same_origin(sitemap_url, origin):
            continue
        if _is_disallowed(sitemap_url, robots_rules):
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            status, body, final_url = _request(sitemap_url, transport, origin, requests_by_host)
        except Exception:
            continue
        if not 200 <= status < 300:
            continue
        page_locs, child_locs = _parse_sitemap(body)
        if child_locs:
            for loc in child_locs:
                child_url = _clean_url(urljoin(final_url, loc))
                if (
                    child_url not in seen_sitemaps
                    and _same_origin(child_url, origin)
                    and len(seen_sitemaps) + len(pending) < MAX_SITEMAP_DOCUMENTS
                ):
                    pending.append(child_url)
        for loc in page_locs:
            page_url = _clean_url(urljoin(final_url, loc))
            if (
                page_url not in seen_pages
                and _same_origin(page_url, origin)
                and not _is_disallowed(page_url, robots_rules)
            ):
                seen_pages.add(page_url)
                pages.append(page_url)
                if len(pages) >= MAX_SITEMAP_URLS:
                    break
    return pages


def crawl_pro(
    start_url,
    transport,
    *,
    max_depth=MAX_CRAWL_DEPTH,
    max_pages=MAX_CRAWL_PAGES,
    respect_robots=True,
):
    """Crawl same-origin links and sitemap URLs through an injected transport.

    Depth and page requests are capped at 3 and 25. Sitemap URLs enter the
    breadth-first queue at depth 1. With ``respect_robots=True``, Disallow
    prefixes from the wildcard robots group are skipped; robots failures fail
    closed except for 404/410. Requests are serial, and ``requests_by_host``
    counts page, robots, and sitemap fetch attempts by hostname.
    """
    if not callable(transport):
        raise TypeError("transport must be callable")
    if not isinstance(respect_robots, bool):
        raise TypeError("respect_robots must be a bool")

    origin = _origin(start_url)
    start_url = _clean_url(start_url)
    depth_limit = _bounded(max_depth, MAX_CRAWL_DEPTH, 0, MAX_CRAWL_DEPTH)
    page_limit = _bounded(max_pages, MAX_CRAWL_PAGES, 1, MAX_CRAWL_PAGES)
    requests_by_host = {}

    robots_rules = (
        _load_robots(start_url, transport, origin, requests_by_host)
        if respect_robots
        else ()
    )
    sitemap_pages = _sitemap_urls(start_url, transport, origin, requests_by_host, robots_rules)

    queue = deque(((start_url, 0),))
    seen = {start_url}
    truncated = False

    def enqueue(url, depth):
        nonlocal truncated
        target = _clean_url(url)
        if target in seen or not _same_origin(target, origin) or _is_disallowed(target, robots_rules):
            return
        if depth > depth_limit:
            truncated = True
            return
        seen.add(target)
        queue.append((target, depth))

    for sitemap_page in sitemap_pages:
        enqueue(sitemap_page, 1)

    pages = []
    while queue and len(pages) < page_limit:
        current, depth = queue.popleft()
        if _is_disallowed(current, robots_rules):
            continue
        status, body, final_url = _request(current, transport, origin, requests_by_host)
        pages.append({"url": current, "depth": depth, "status": status, "content": body})

        if not 200 <= status < 300:
            continue
        parser = _LinkParser()
        parser.feed(body)
        parser.close()
        for href in parser.links:
            target = _clean_url(urljoin(final_url, href))
            enqueue(target, depth + 1)

    if queue:
        truncated = True
    return {
        "ok": True,
        "pages": pages,
        "truncated": truncated,
        "requests_by_host": dict(requests_by_host),
    }
