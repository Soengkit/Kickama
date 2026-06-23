import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import health_check


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class HealthCheckRateLimiterTest(unittest.TestCase):
    def test_token_bucket_throttles_after_burst(self):
        clock = FakeClock()
        limiter = health_check.ProbeRateLimiter(
            1.0,
            burst=1.0,
            clock=clock.monotonic,
            sleep_fn=clock.sleep,
        )

        limiter.wait()
        limiter.wait()

        stats = limiter.stats()
        self.assertEqual(stats["total_probes"], 2)
        self.assertEqual(stats["throttled_requests"], 1)
        self.assertEqual(clock.sleeps, [1.0])

    def test_half_open_probe_uses_reduced_rate(self):
        clock = FakeClock()
        limiter = health_check.ProbeRateLimiter(
            4.0,
            burst=1.0,
            clock=clock.monotonic,
            sleep_fn=clock.sleep,
        )

        limiter.wait(half_open=True)

        stats = limiter.stats()
        self.assertEqual(stats["current_rate"], 2.0)
        self.assertEqual(stats["half_open_reductions"], 1)

    def test_timeout_overrides_are_applied_to_service_checks(self):
        calls = []

        def http_checker(host, port, path, timeout):
            calls.append(("http", host, port, path, timeout))
            return "OK", "HTTP 200", 200

        def tcp_checker(host, port, timeout):
            calls.append(("tcp", host, port, timeout))
            return "OK", "Connected", 1.0

        results = health_check.run_health_checks(
            service="backend",
            timeout=3.0,
            service_timeouts={"backend": 1.25},
            probe_rate=5.0,
            half_open_services={"backend"},
            http_checker=http_checker,
            tcp_checker=tcp_checker,
        )

        self.assertEqual(calls, [("http", "localhost", 8080, "/health", 1.25)])
        self.assertEqual(results["services"]["backend"]["timeout_seconds"], 1.25)
        self.assertTrue(results["services"]["backend"]["half_open_rate_reduced"])
        self.assertEqual(results["rate_limiter"]["current_rate"], 2.5)
        self.assertEqual(results["services"]["backend"]["status"], "OK")

    def test_service_timeout_parser_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            health_check.parse_service_timeout_overrides(["backend"])
        with self.assertRaises(ValueError):
            health_check.parse_service_timeout_overrides(["backend=0"])

    def test_positive_option_validator_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            health_check.validate_positive_option("--probe-rate", 0)
        health_check.validate_positive_option("--probe-rate", 1)


if __name__ == "__main__":
    unittest.main()
