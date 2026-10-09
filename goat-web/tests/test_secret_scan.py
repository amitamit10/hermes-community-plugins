import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from audit_staging import scan_staging  # noqa: E402


class SecretScanTests(unittest.TestCase):
    def test_all_required_secret_markers_are_detected(self):
        markers = (
            b"AK" + b"IA",
            b"ghp" + b"_",
            b"xoxb" + b"-",
            b"BEGIN PRIVATE" + b" KEY",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index, marker in enumerate(markers):
                (root / ("fixture" + str(index) + ".txt")).write_bytes(b"prefix " + marker + b" suffix")
            findings = scan_staging(root)
            self.assertEqual(len(findings), len(markers))
            self.assertTrue(all(kind == "secret-pattern" for kind, _path in findings))

    def test_absolute_path_patterns_are_detected(self):
        markers = (b"/" + b"opt/", b"/" + b"home/")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "fixture.txt").write_bytes(b" ".join(markers))
            findings = scan_staging(root)
            self.assertEqual(findings, [("absolute-path", "fixture.txt")] * 2)


if __name__ == "__main__":
    unittest.main()
