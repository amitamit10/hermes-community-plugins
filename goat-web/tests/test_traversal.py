import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from audit_staging import scan_staging  # noqa: E402


class StagingTraversalTests(unittest.TestCase):
    def test_audit_is_confined_to_the_supplied_tree(self):
        marker = b"AK" + b"IA"
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            staging = parent / "project" / "staging"
            staging.mkdir(parents=True)
            (parent / "outside.txt").write_bytes(b"external marker: " + marker)
            self.assertEqual(scan_staging(staging), [])

    def test_nested_files_are_scanned_without_leaving_the_root(self):
        marker = b"ghp" + b"_"
        with tempfile.TemporaryDirectory() as temp_dir:
            staging = Path(temp_dir) / "staging"
            nested = staging / "nested" / "deeper"
            nested.mkdir(parents=True)
            (nested / "sample.txt").write_bytes(b"fixture " + marker)
            findings = scan_staging(staging)
            self.assertEqual(findings, [("secret-pattern", "nested/deeper/sample.txt")])

    def test_file_symlink_is_reported_without_following_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            staging = base / "staging"
            staging.mkdir()
            target = base / "outside.txt"
            target.write_bytes(b"AK" + b"IA" + b"not-a-real-secret")
            (staging / "linked-file.txt").symlink_to(target)
            self.assertEqual(scan_staging(staging), [("symlink", "linked-file.txt")])

    def test_directory_symlink_is_reported_without_walking_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            staging = base / "staging"
            staging.mkdir()
            target = base / "outside-dir"
            target.mkdir()
            (target / "sample.txt").write_bytes(b"ghp" + b"_not-a-real-token")
            (staging / "linked-dir").symlink_to(target, target_is_directory=True)
            self.assertEqual(scan_staging(staging), [("symlink", "linked-dir")])

    def test_symlink_staging_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            target = base / "real-root"
            target.mkdir()
            root_link = base / "root-link"
            root_link.symlink_to(target, target_is_directory=True)
            self.assertEqual(scan_staging(root_link), [("symlink", ".")])

    def test_symlink_parent_of_staging_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            target_parent = base / "real-parent"
            staging = target_parent / "project" / "staging"
            staging.mkdir(parents=True)
            parent_link = base / "parent-link"
            parent_link.symlink_to(target_parent, target_is_directory=True)
            self.assertEqual(
                scan_staging(parent_link / "project" / "staging"),
                [("symlink", ".")],
            )


if __name__ == "__main__":
    unittest.main()
