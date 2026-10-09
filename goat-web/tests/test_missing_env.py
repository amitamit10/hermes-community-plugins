import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from audit_staging import scan_staging  # noqa: E402


class MissingEnvAuditTests(unittest.TestCase):
    def test_env_and_auth_files_are_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text("placeholder", encoding="utf-8")
            (root / "auth.json").write_text("{}", encoding="utf-8")
            findings = scan_staging(root)
            self.assertEqual(
                findings,
                [("sensitive-file", ".env"), ("sensitive-file", "auth.json")],
            )

    def test_safe_files_do_not_look_like_env_or_auth_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("documentation", encoding="utf-8")
            (root / "example.env.template").write_text("placeholder", encoding="utf-8")
            self.assertEqual(scan_staging(root), [])


if __name__ == "__main__":
    unittest.main()
