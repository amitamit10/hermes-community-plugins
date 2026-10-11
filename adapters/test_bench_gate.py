import contextlib
import io
import os
import runpy
import tempfile
import unittest
from pathlib import Path

import bench_gate
import bench_modules


class BenchGateTests(unittest.TestCase):
    def test_load_gate_succeeds_independent_of_cwd(self):
        canonical = Path(__file__).resolve().parents[1] / "goat-web" / "plugins" / "goat-web" / "url_gate.py"
        previous_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.chdir(tmpdir)
                try:
                    gate = bench_gate.load_gate()
                except FileNotFoundError as exc:
                    self.fail(str(exc))
                self.assertEqual(bench_gate.REFERENCE, canonical)
                self.assertEqual(gate.check_url("https://example.com/article"), (True, gate.OK))
                self.assertFalse(gate.check_url("https://localhost/article")[0])
                self.assertEqual(gate.check_redirect("https://example.com/start", "/next?case=1", 0), (True, gate.OK))
            finally:
                os.chdir(previous_cwd)

    def test_benchmark_entry_runs_both_suites_offline(self):
        entry = Path(__file__).resolve().parents[1] / "benchmarks" / "run.py"
        previous_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.chdir(tmpdir)
                buffer = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buffer):
                        runpy.run_path(str(entry), run_name="__main__")
                except FileNotFoundError:
                    self.fail(f"Benchmark entry is missing: {entry}")
                output = buffer.getvalue()
            finally:
                os.chdir(previous_cwd)
        self.assertIn("offline", output.lower())
        self.assertIn("perf_counter_ns", output)
        names = [line.split("|")[1].strip().strip("`") for line in output.splitlines() if line.strip().startswith("| `")]
        self.assertEqual(names, ["check_url", "check_redirect"] + list(bench_modules.MODULES))


if __name__ == "__main__":
    unittest.main()
