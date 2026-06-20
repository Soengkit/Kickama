#!/usr/bin/env python3

import json
import unittest
from datetime import datetime, timezone

import health_check


class HealthCheckStaleMetricsTests(unittest.TestCase):
    def sample_results(self, timestamp):
        return {
            "timestamp": timestamp,
            "hostname": "test-host",
            "services": {
                "backend": {
                    "status": "OK",
                    "detail": "HTTP 200 token=secret-value",
                }
            },
            "infrastructure": {},
            "system": {
                "disk": {
                    "status": "WARNING",
                    "detail": "85% used",
                }
            },
            "overall_status": "OK",
        }

    def test_fresh_metric_rows_are_not_stale(self):
        now = datetime(2026, 6, 20, 15, 0, 0, tzinfo=timezone.utc)
        rows = health_check.health_metric_rows(
            self.sample_results("2026-06-20T14:59:00+00:00"),
            "staging",
            300,
            now,
        )

        self.assertEqual(rows[0]["service"], "backend")
        self.assertEqual(rows[0]["environment"], "staging")
        self.assertFalse(rows[0]["stale"])
        self.assertEqual(rows[0]["age_seconds"], 60)

    def test_stale_metric_rows_are_flagged_with_age(self):
        now = datetime(2026, 6, 20, 15, 10, 0, tzinfo=timezone.utc)
        rows = health_check.health_metric_rows(
            self.sample_results("2026-06-20T15:00:00+00:00"),
            "production",
            300,
            now,
        )

        self.assertTrue(rows[0]["stale"])
        self.assertEqual(rows[0]["age_seconds"], 600)

    def test_json_rows_include_required_fields_and_redact_details(self):
        rows = health_check.health_metric_rows(
            self.sample_results("not-a-timestamp"),
            "production",
            300,
        )

        encoded = json.dumps(rows)
        self.assertIn("metric_name", rows[0])
        self.assertIn("timestamp", rows[0])
        self.assertTrue(rows[0]["stale"])
        self.assertNotIn("secret-value", encoded)
        self.assertIn("token=[REDACTED]", encoded)

    def test_prometheus_output_includes_stale_guard_metrics(self):
        now = datetime(2026, 6, 20, 15, 0, 0, tzinfo=timezone.utc)
        rows = health_check.health_metric_rows(
            self.sample_results("2026-06-20T14:50:00+00:00"),
            "production",
            300,
            now,
        )

        output = health_check.render_prometheus_metrics(rows)

        self.assertIn("tent_health_status", output)
        self.assertIn("tent_health_metric_stale", output)
        self.assertIn('service="backend"', output)
        self.assertIn('environment="production"', output)
        self.assertIn(" 1", output)


if __name__ == "__main__":
    unittest.main()
