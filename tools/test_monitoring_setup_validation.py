#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import monitoring_setup


def write_required_dashboards(dashboard_dir):
    os.makedirs(dashboard_dir, exist_ok=True)
    for dashboard in monitoring_setup.REQUIRED_DASHBOARDS:
        filename = f"{dashboard['uid']}.json"
        with open(os.path.join(dashboard_dir, filename), "w", encoding="utf-8") as f:
            json.dump({"title": dashboard["title"], "uid": dashboard["uid"]}, f)


def make_args(dashboard_dir, slack_webhook="https://hooks.example.com/alerts",
              pagerduty_key="0123456789abcdef"):
    return argparse.Namespace(
        dashboard_dir=dashboard_dir,
        alert_rules_dir="unused",
        slack_webhook=slack_webhook,
        pagerduty_key=pagerduty_key,
    )


class MonitoringValidationTests(unittest.TestCase):
    def test_validate_only_accepts_valid_local_config_without_network_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_required_dashboards(tmp)
            args = make_args(tmp)

            with mock.patch.object(monitoring_setup, "http_request", side_effect=AssertionError):
                report = monitoring_setup.validate_monitoring_config(args)

        self.assertTrue(report["ok"], report)
        self.assertEqual([], report["errors"])
        self.assertEqual(5, report["summary"]["dashboards_checked"])
        self.assertEqual(len(monitoring_setup.RECOMMENDED_ALERT_RULES),
                         report["summary"]["alert_rules_checked"])
        self.assertEqual(2, report["summary"]["notification_targets_checked"])

    def test_validate_only_reports_all_local_config_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "system.json"), "w", encoding="utf-8") as f:
                json.dump({"title": "System Overview", "uid": "tot-system-overview"}, f)

            args = make_args(tmp, slack_webhook="http://hooks.example.com/alerts",
                             pagerduty_key="short")
            report = monitoring_setup.validate_monitoring_config(args)

        self.assertFalse(report["ok"])
        joined = "\n".join(report["errors"])
        self.assertIn("Missing required dashboard: API Performance", joined)
        self.assertIn("Slack webhook must use https://", joined)
        self.assertIn("PagerDuty routing key is too short", joined)
        self.assertGreaterEqual(len(report["errors"]), 5)

    def test_alert_rule_validation_collects_multiple_errors(self):
        report = {
            "errors": [],
            "warnings": [],
            "summary": {"alert_rules_checked": 0},
        }
        bad_rules = [
            {"name": "ServiceDown", "expr": "up", "duration": "", "severity": "urgent"},
            {"name": "ServiceDown", "expr": "", "duration": "5m", "severity": "critical"},
        ]

        monitoring_setup.validate_alert_rules(bad_rules, report)

        joined = "\n".join(report["errors"])
        self.assertIn("Alert rule ServiceDown has no numeric threshold in expr", joined)
        self.assertIn("Alert rule ServiceDown is missing duration", joined)
        self.assertIn("Alert rule ServiceDown has invalid severity: urgent", joined)
        self.assertIn("Duplicate alert rule name: ServiceDown", joined)
        self.assertIn("Missing required alert rule: HighLatency", joined)
        self.assertEqual(2, report["summary"]["alert_rules_checked"])

    def test_cli_validate_only_returns_nonzero_for_invalid_config(self):
        script = os.path.join(os.path.dirname(__file__), "monitoring_setup.py")
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    script,
                    "--validate-only",
                    "--dashboard-dir",
                    tmp,
                    "--slack-webhook",
                    "http://hooks.example.com/alerts",
                    "--pagerduty-key",
                    "short",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("Errors:", result.stdout)
        self.assertIn("Slack webhook must use https://", result.stdout)


if __name__ == "__main__":
    unittest.main()
