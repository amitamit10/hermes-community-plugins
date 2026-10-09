"""Shared DuckDuckGo HTML parser for goat-packs.

Single canonical implementation used by both ``free_search`` and
``free_stack`` so the HTML ``result__a`` / ``result__snippet`` contract
is exercised from one place. Keep this module stdlib-only (HTMLParser).
"""

from html.parser import HTMLParser

_VOID_TAGS = frozenset(
    ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr")
)


class _SearchParser(HTMLParser):
    """Parse DuckDuckGo HTML lite results — anchor + snippet pairs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.snippets = []
        self._capture = None
        self._stack = []

    def _finish_capture(self):
        kind, href, chunks = self._capture
        text = " ".join("".join(chunks).split())
        if kind == "result":
            self.results.append({"url": href, "title": text})
        else:
            self.snippets.append(text)
        self._capture = None
        self._stack = []

    def handle_starttag(self, tag, attrs):
        lowered = tag.lower()
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if self._capture is not None:
            if lowered not in _VOID_TAGS:
                self._stack.append(lowered)
            return
        if lowered == "a" and "result__a" in classes:
            self._capture = ("result", attributes.get("href", ""), [])
            self._stack = [lowered]
        elif "result__snippet" in classes:
            self._capture = ("snippet", "", [])
            self._stack = [lowered]

    def handle_endtag(self, tag):
        if self._capture is None:
            return
        lowered = tag.lower()
        if lowered not in self._stack:
            return
        index = len(self._stack) - 1 - self._stack[::-1].index(lowered)
        self._stack = self._stack[:index]
        if not self._stack:
            self._finish_capture()

    def handle_data(self, data):
        if self._capture is not None:
            self._capture[2].append(data)

    def close(self):
        super().close()
        if self._capture is not None:
            self._finish_capture()


class _PlainTextParser(HTMLParser):
    """Strip tags and return whitespace-normalized text (used for wiki snippets)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain_text(value):
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    parser = _PlainTextParser()
    parser.feed(value)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


__all__ = ["_VOID_TAGS", "_SearchParser", "_PlainTextParser", "_plain_text"]
