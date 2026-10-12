"""Round4 priority4 tracer: filtered-search source metadata (RED)."""
import importlib.util
import json
import shutil
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "test_v3_wiring", Path(__file__).with_name("test_v3_wiring.py")
)
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)

OfflineTestCase = _mod.OfflineTestCase
build_fixture_package = _mod.build_fixture_package
load_fixture_package = _mod.load_fixture_package
unload_fixture_package = _mod.unload_fixture_package
RecordingContext = _mod.RecordingContext


def _ml_body():
    return json.dumps(
        {
            "query": {
                "search": [
                    {
                        "title": "Machine learning",
                        "snippet": "Machine learning is a field of study in artificial intelligence.",
                    }
                ]
            }
        }
    ).encode("utf-8")


class R4FilterMetadataTests(OfflineTestCase):
    def test_english_wikipedia_candidate_survives_english_filter(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)

        def fake_fetch(url, **kwargs):
            return {
                "status": 200,
                "headers": {},
                "body": _ml_body(),
                "url": url,
            }

        search = module.v3_wiring.make_default_search(_fetch=fake_fetch)
        deps = module.v3_wiring.WiringDependencies(
            search=search, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_filtered_search"]["handler"]
        payload = json.loads(
            handler(
                {
                    "query": "machine learning",
                    "allowed_domains": ["en.wikipedia.org"],
                    "language": "en",
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        results = payload.get("results", [])
        self.assertGreaterEqual(len(results), 1, payload)
        self.assertTrue(
            any(item.get("language") == "en" for item in results), payload
        )

    def test_denied_wikipedia_wins_over_allow(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)

        def fake_fetch(url, **kwargs):
            return {
                "status": 200,
                "headers": {},
                "body": _ml_body(),
                "url": url,
            }

        search = module.v3_wiring.make_default_search(_fetch=fake_fetch)
        deps = module.v3_wiring.WiringDependencies(
            search=search, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_filtered_search"]["handler"]
        payload = json.loads(
            handler(
                {
                    "query": "machine learning",
                    "allowed_domains": ["en.wikipedia.org"],
                    "denied_domains": ["en.wikipedia.org"],
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(payload.get("results"), [], payload)

    def test_english_candidate_excluded_by_fr_and_regional_but_survives_en(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)

        def fake_fetch(url, **kwargs):
            return {
                "status": 200,
                "headers": {},
                "body": _ml_body(),
                "url": url,
            }

        search = module.v3_wiring.make_default_search(_fetch=fake_fetch)
        deps = module.v3_wiring.WiringDependencies(
            search=search, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_filtered_search"]["handler"]

        survived = json.loads(
            handler({"query": "machine learning", "language": "en"})
        )
        self.assertTrue(survived.get("ok"), survived)
        self.assertGreaterEqual(len(survived.get("results", [])), 1, survived)

        excluded_fr = json.loads(
            handler({"query": "machine learning", "language": "fr"})
        )
        self.assertTrue(excluded_fr.get("ok"), excluded_fr)
        self.assertEqual(excluded_fr.get("results"), [], excluded_fr)

        excluded_regional = json.loads(
            handler({"query": "machine learning", "language": "en-US"})
        )
        self.assertTrue(excluded_regional.get("ok"), excluded_regional)
        self.assertEqual(excluded_regional.get("results"), [], excluded_regional)

    def test_time_filter_excludes_undated_without_invented_date(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)

        def fake_fetch(url, **kwargs):
            return {
                "status": 200,
                "headers": {},
                "body": _ml_body(),
                "url": url,
            }

        search = module.v3_wiring.make_default_search(_fetch=fake_fetch)
        deps = module.v3_wiring.WiringDependencies(
            search=search, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_filtered_search"]["handler"]

        unfiltered = json.loads(handler({"query": "machine learning"}))
        self.assertTrue(unfiltered.get("ok"), unfiltered)
        self.assertGreaterEqual(len(unfiltered.get("results", [])), 1, unfiltered)
        date_fields = (
            "published_at",
            "publishedAt",
            "published_date",
            "publication_date",
            "published",
            "date",
            "datetime",
            "timestamp",
            "created_at",
        )
        for item in unfiltered.get("results", []):
            for field in date_fields:
                self.assertNotIn(field, item, unfiltered)

        filtered = json.loads(
            handler(
                {
                    "query": "machine learning",
                    "time_after": "2020-01-01T00:00:00Z",
                }
            )
        )
        self.assertTrue(filtered.get("ok"), filtered)
        self.assertEqual(filtered.get("results"), [], filtered)

    def test_generic_backend_missing_language_stays_excluded_no_inference(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)

        def fake_search(query, *, max_results=5):
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Machine learning",
                        "url": "https://en.wikipedia.org/wiki/Machine_learning",
                        "snippet": "Machine learning summary.",
                    }
                ],
                "source": "wikipedia",
                "source_url": "https://en.wikipedia.org/w/api.php",
                "truncated": False,
            }

        deps = module.v3_wiring.WiringDependencies(
            search=fake_search, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_filtered_search"]["handler"]

        unfiltered = json.loads(handler({"query": "machine learning"}))
        self.assertTrue(unfiltered.get("ok"), unfiltered)
        self.assertGreaterEqual(len(unfiltered.get("results", [])), 1, unfiltered)

        filtered = json.loads(
            handler({"query": "machine learning", "language": "en"})
        )
        self.assertTrue(filtered.get("ok"), filtered)
        self.assertEqual(filtered.get("results"), [], filtered)

    def test_foreign_fullurl_never_labeled_english_never_regional(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)

        body = json.dumps(
            {
                "query": {
                    "search": [
                        {
                            "title": "Bonjour",
                            "fullurl": "https://fr.wikipedia.org/wiki/Bonjour",
                            "snippet": "French greeting.",
                        },
                        {
                            "title": "Unknown page",
                            "fullurl": "https://example.org/unknown-page",
                            "snippet": "Unknown host page.",
                        },
                    ]
                }
            }
        ).encode("utf-8")

        def fake_fetch(url, **kwargs):
            return {"status": 200, "headers": {}, "body": body, "url": url}

        search = module.v3_wiring.make_default_search(_fetch=fake_fetch)
        deps = module.v3_wiring.WiringDependencies(
            search=search, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_filtered_search"]["handler"]

        unfiltered = json.loads(handler({"query": "bonjour"}))
        self.assertTrue(unfiltered.get("ok"), unfiltered)
        self.assertGreaterEqual(len(unfiltered.get("results", [])), 1, unfiltered)
        for item in unfiltered.get("results", []):
            lang = item.get("language")
            self.assertNotEqual((lang or "").lower(), "en", unfiltered)
            self.assertFalse(
                (lang or "").lower().startswith("en-"), unfiltered
            )

        excluded_en = json.loads(
            handler({"query": "bonjour", "language": "en"})
        )
        self.assertTrue(excluded_en.get("ok"), excluded_en)
        self.assertEqual(excluded_en.get("results"), [], excluded_en)

        excluded_regional = json.loads(
            handler({"query": "bonjour", "language": "en-US"})
        )
        self.assertTrue(excluded_regional.get("ok"), excluded_regional)
        self.assertEqual(excluded_regional.get("results"), [], excluded_regional)


if __name__ == "__main__":
    unittest.main()
