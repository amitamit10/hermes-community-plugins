"""Offline tests for the RSS watcher; the fake transport never uses a socket."""

import tempfile
import unittest
from pathlib import Path

from rss_watcher import RSSWatcher, parse_feed


FEED_AB = """<rss version="2.0"><channel>
<item><guid>a</guid><title>Alpha</title><link>https://example.test/a</link></item>
<item><guid>b</guid><title>Beta</title><link>https://example.test/b</link></item>
</channel></rss>"""

FEED_CAB = """<rss version="2.0"><channel>
<item><guid>c</guid><title>Gamma</title><link>https://example.test/c</link></item>
<item><guid>a</guid><title>Alpha</title><link>https://example.test/a</link></item>
<item><guid>b</guid><title>Beta</title><link>https://example.test/b</link></item>
</channel></rss>"""


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.responses[url]


class RSSWatcherTests(unittest.TestCase):
    def test_parse_rss_items_and_guid(self):
        items = parse_feed(FEED_AB.encode("utf-8"))
        self.assertEqual([item["id"] for item in items], ["a", "b"])
        self.assertEqual(items[0]["title"], "Alpha")
        self.assertEqual(items[0]["url"], "https://example.test/a")

    def test_poll_returns_unseen_only_and_deduplicates(self):
        transport = FakeTransport({
            "https://example.test/feed": {"status": 200, "body": FEED_AB},
        })
        watcher = RSSWatcher(transport)
        first = watcher.poll("https://example.test/feed")
        second = watcher.poll("https://example.test/feed")
        self.assertEqual([item["id"] for item in first], ["a", "b"])
        self.assertEqual(second, [])
        self.assertEqual(transport.calls, ["https://example.test/feed"] * 2)

    def test_max_items_leaves_overflow_unseen_for_next_poll(self):
        transport = FakeTransport({"feed": FEED_AB})
        watcher = RSSWatcher(transport, max_items=1)
        self.assertEqual([item["id"] for item in watcher.poll("feed")], ["a"])
        self.assertEqual([item["id"] for item in watcher.poll("feed")], ["b"])
        self.assertEqual(watcher.poll("feed"), [])

    def test_state_path_persists_dedup_across_instances(self):
        transport = FakeTransport({"feed": FEED_AB})
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "watermark.json"
            first_watcher = RSSWatcher(transport, state_path=state_path)
            self.assertEqual([item["id"] for item in first_watcher.poll("feed")], ["a", "b"])
            second_watcher = RSSWatcher(transport, state_path=state_path)
            self.assertEqual(second_watcher.poll("feed"), [])
            self.assertEqual(second_watcher.seen_ids, ("a", "b"))

    def test_atom_feed_and_new_item(self):
        atom = """<feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>urn:one</id><title>One</title><link href="https://example.test/one"/>
<updated>2026-10-09T08:00:00Z</updated><summary>Brief</summary></entry>
</feed>"""
        self.assertEqual(parse_feed(atom)[0], {
            "id": "urn:one",
            "title": "One",
            "url": "https://example.test/one",
            "summary": "Brief",
            "published": "2026-10-09T08:00:00Z",
        })

    def test_fetch_error_does_not_advance_watermark(self):
        transport = FakeTransport({"feed": {"status": 503, "body": FEED_AB}})
        watcher = RSSWatcher(transport)
        with self.assertRaisesRegex(RuntimeError, "503"):
            watcher.poll("feed")
        self.assertEqual(watcher.seen_ids, ())


if __name__ == "__main__":
    unittest.main()
