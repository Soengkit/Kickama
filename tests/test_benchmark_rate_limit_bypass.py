import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import benchmark


class BenchmarkRateLimitBypassTest(unittest.TestCase):
    def test_build_request_headers_is_opt_in(self):
        self.assertEqual(benchmark.build_request_headers(False), {})
        self.assertEqual(
            benchmark.build_request_headers(True),
            {"X-Benchmark-Bypass-Rate-Limit": "true"},
        )

    def test_worker_propagates_bypass_header_to_requests(self):
        seen_headers = []

        def fake_make_request(url, method="GET", timeout=30.0, headers=None):
            seen_headers.append(headers)
            return 200, 1.0, None

        with mock.patch.object(benchmark, "make_request", side_effect=fake_make_request):
            results = []
            benchmark.run_worker(
                "http://example.test/health",
                request_count=2,
                results=results,
                stop_flag=threading.Event(),
                timeout=1.0,
                headers=benchmark.build_request_headers(True),
            )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            seen_headers,
            [
                {"X-Benchmark-Bypass-Rate-Limit": "true"},
                {"X-Benchmark-Bypass-Rate-Limit": "true"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
