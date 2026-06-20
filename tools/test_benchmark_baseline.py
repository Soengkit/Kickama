#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("benchmark.py")
SPEC = importlib.util.spec_from_file_location("benchmark_tool", MODULE_PATH)
benchmark_tool = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark_tool)


def make_result(rps=100.0, p95=200.0, failed=0):
    return benchmark_tool.BenchmarkResult(
        benchmark_type="latency",
        start_time=1.0,
        end_time=2.0,
        duration_seconds=1.0,
        total_requests=100,
        successful_requests=100 - failed,
        failed_requests=failed,
        timeout_requests=0,
        requests_per_second=rps,
        latency_ms={
            "min": 10.0,
            "p50": 100.0,
            "p90": 180.0,
            "p95": p95,
            "p99": 250.0,
            "max": 300.0,
            "avg": 120.0,
            "stddev": 12.0,
        },
        error_distribution={},
        target_endpoint="http://localhost:8080/health",
        concurrency=4,
    )


class BenchmarkBaselineTest(unittest.TestCase):
    def test_write_and_load_baseline_is_deterministic_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline_path = Path(tmpdir) / "baseline.json"
            benchmark_tool.write_baseline(str(baseline_path), make_result())

            payload = json.loads(baseline_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["benchmark_type"], "latency")
            self.assertEqual(payload["latency_ms"]["p95"], 200.0)
            self.assertEqual(
                benchmark_tool.load_baseline(str(baseline_path))["requests_per_second"],
                100.0,
            )

    def test_comparison_marks_rps_drop_and_latency_increase_as_regressions(self):
        baseline = benchmark_tool.result_to_dict(make_result(rps=100.0, p95=200.0))
        current = make_result(rps=90.0, p95=250.0)

        comparison = benchmark_tool.compare_with_baseline(current, baseline)
        by_metric = {entry["metric"]: entry for entry in comparison["comparisons"]}

        self.assertTrue(by_metric["requests_per_second"]["regression"])
        self.assertAlmostEqual(by_metric["requests_per_second"]["percent_change"], -10.0)
        self.assertTrue(by_metric["latency_ms.p95"]["regression"])
        self.assertAlmostEqual(by_metric["latency_ms.p95"]["percent_change"], 25.0)
        self.assertAlmostEqual(comparison["max_regression_percent"], 25.0)

    def test_improved_metrics_are_not_regressions(self):
        baseline = benchmark_tool.result_to_dict(make_result(rps=100.0, p95=200.0, failed=2))
        current = make_result(rps=120.0, p95=150.0, failed=0)

        comparison = benchmark_tool.compare_with_baseline(current, baseline)
        regressions = [entry for entry in comparison["comparisons"] if entry["regression"]]

        self.assertEqual(regressions, [])
        self.assertEqual(comparison["max_regression_percent"], 0)


if __name__ == "__main__":
    unittest.main()
