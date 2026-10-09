import unittest

import bench_modules


class BenchModulesTests(unittest.TestCase):
    def test_benchmark_runs_all_modules_and_returns_latency_statistics(self):
        results = bench_modules.run_benchmarks(3, 1)

        self.assertEqual(set(results), set(bench_modules.MODULES))
        self.assertGreaterEqual(len(results), 10)
        self.assertEqual(len(results), 17)
        for name, stats in results.items():
            with self.subTest(module=name):
                self.assertEqual(set(stats), {"iterations", "mean_ns", "p50_ns", "p99_ns"})
                self.assertEqual(stats["iterations"], 3)
                for metric in ("mean_ns", "p50_ns", "p99_ns"):
                    self.assertIsInstance(stats[metric], (int, float))
                    self.assertGreater(stats[metric], 0)


if __name__ == "__main__":
    unittest.main()
