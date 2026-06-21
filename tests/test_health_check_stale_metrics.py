"""
Tests for the health check Prometheus stale-metric guard.

Covers fresh and stale metric detection, the required JSON fields,
Prometheus exposition formatting, secret redaction, and default
output compatibility.
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from health_check import (
    collect_health_metrics,
    flag_stale_metrics,
    format_prometheus,
    redact_secrets,
)


def _sample_results(timestamp=None):
    return {
        "timestamp": timestamp or datetime.now().isoformat(),
        "hostname": "test-host",
        "services": {
            "backend": {"status": "OK", "detail": "HTTP 200", "code": 200, "endpoint": "http://localhost:8080/health"},
        },
        "infrastructure": {
            "redis": {"status": "OK", "detail": "Connected", "endpoint": "localhost:6379"},
        },
        "system": {
            "disk": {"status": "OK", "detail": "40.0% used"},
            "memory": {"status": "WARNING", "detail": "82.0% used"},
        },
        "overall_status": "DEGRADED",
    }


class TestCollectHealthMetrics(unittest.TestCase):
    def test_includes_required_fields(self):
        metrics = collect_health_metrics(_sample_results(), environment="staging")
        self.assertGreater(len(metrics), 0)
        for m in metrics:
            self.assertIn("service", m)
            self.assertIn("environment", m)
            self.assertEqual(m["environment"], "staging")
            self.assertIn("metric_name", m)
            self.assertIn("timestamp", m)
            self.assertIn("status", m)

    def test_covers_all_categories(self):
        metrics = collect_health_metrics(_sample_results())
        names = {m["metric_name"] for m in metrics}
        self.assertIn("service.backend.status", names)
        self.assertIn("infrastructure.redis.status", names)
        self.assertIn("system.disk.status", names)
        self.assertIn("system.memory.status", names)


class TestStaleMetricGuard(unittest.TestCase):
    def test_fresh_metrics_not_stale(self):
        now = datetime.now()
        ts = (now - timedelta(seconds=10)).isoformat()
        flagged = flag_stale_metrics(collect_health_metrics(_sample_results(timestamp=ts)), now=now, threshold=300)
        self.assertTrue(flagged)
        for m in flagged:
            self.assertFalse(m["stale"], f"{m['metric_name']} should be fresh")
            self.assertIsNotNone(m["age_seconds"])
            self.assertLessEqual(m["age_seconds"], 11)

    def test_stale_metrics_flagged_with_age(self):
        now = datetime.now()
        ts = (now - timedelta(seconds=3600)).isoformat()
        flagged = flag_stale_metrics(collect_health_metrics(_sample_results(timestamp=ts)), now=now, threshold=300)
        for m in flagged:
            self.assertTrue(m["stale"], f"{m['metric_name']} should be stale")
            self.assertIsNotNone(m["age_seconds"])
            self.assertGreater(m["age_seconds"], 300)

    def test_threshold_boundary(self):
        now = datetime.now()
        under = flag_stale_metrics(
            collect_health_metrics(_sample_results(timestamp=(now - timedelta(seconds=299)).isoformat())),
            now=now, threshold=300,
        )
        over = flag_stale_metrics(
            collect_health_metrics(_sample_results(timestamp=(now - timedelta(seconds=301)).isoformat())),
            now=now, threshold=300,
        )
        self.assertFalse(any(m["stale"] for m in under))
        self.assertTrue(all(m["stale"] for m in over))

    def test_missing_timestamp_is_stale(self):
        metrics = [{"service": "backend", "environment": "prod", "metric_name": "service.backend.status", "timestamp": None, "status": "OK"}]
        flagged = flag_stale_metrics(metrics, now=datetime.now(), threshold=300)
        self.assertTrue(flagged[0]["stale"])
        self.assertIsNone(flagged[0]["age_seconds"])


class TestPrometheusFormat(unittest.TestCase):
    def test_emits_help_type_and_metrics(self):
        text = format_prometheus(_sample_results(), threshold=300)
        self.assertIn("# HELP tot_health_check_status", text)
        self.assertIn("# TYPE tot_health_check_status gauge", text)
        self.assertIn("# HELP tot_health_check_metric_stale", text)
        self.assertIn("tot_health_check_status{", text)
        self.assertIn("tot_health_check_metric_stale{", text)

    def test_stale_flag_exported(self):
        now = datetime.now()
        ts = (now - timedelta(seconds=3600)).isoformat()
        text = format_prometheus(_sample_results(timestamp=ts), now=now, threshold=300)
        self.assertRegex(text, r'tot_health_check_metric_stale\{[^}]*\} 1')

    def test_fresh_flag_zero(self):
        now = datetime.now()
        ts = (now - timedelta(seconds=5)).isoformat()
        text = format_prometheus(_sample_results(timestamp=ts), now=now, threshold=300)
        self.assertRegex(text, r'tot_health_check_metric_stale\{[^}]*\} 0')


class TestRedaction(unittest.TestCase):
    def test_redacts_passwords_and_tokens(self):
        text = "password=hunter2 token=abc123 ghp_" + "x" * 30
        redacted = redact_secrets(text)
        self.assertNotIn("hunter2", redacted)
        self.assertIn("REDACTED", redacted)
        self.assertNotIn("ghp_" + "x" * 30, redacted)

    def test_redaction_preserves_keys(self):
        self.assertIn("api_key=REDACTED", redact_secrets("api_key=supersecret123"))


class TestDefaultCompatibility(unittest.TestCase):
    def test_results_structure_preserved(self):
        results = _sample_results()
        results["stale_metrics"] = flag_stale_metrics(collect_health_metrics(results))
        for key in ("timestamp", "hostname", "services", "infrastructure", "system", "overall_status"):
            self.assertIn(key, results)


if __name__ == "__main__":
    unittest.main()
