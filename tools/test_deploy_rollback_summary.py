#!/usr/bin/env python3

import io
import json
import unittest
from contextlib import redirect_stdout

import deploy


class RollbackSummaryTests(unittest.TestCase):
    def test_build_rollback_summary_includes_required_fields(self):
        summary = deploy.build_rollback_summary("backend", "production", "v3.1.0")

        self.assertEqual(summary["mode"], "rollback-dry-run")
        self.assertEqual(summary["service"], "backend")
        self.assertEqual(summary["environment"], "production")
        self.assertEqual(summary["version"], "v3.1.0")
        self.assertIn("planned_actions", summary)
        self.assertIn("risk_notes", summary)
        self.assertIn("rollback_steps", summary)
        self.assertGreaterEqual(len(summary["planned_actions"]), 3)
        self.assertIn("namespace", summary["target"])

    def test_json_summary_output_is_machine_readable(self):
        summary = deploy.build_rollback_summary("frontend", "staging", "v2.9.0")
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            deploy.print_rollback_summary(summary, "json")

        parsed = json.loads(stdout.getvalue())
        self.assertEqual(parsed["service"], "frontend")
        self.assertEqual(parsed["environment"], "staging")
        self.assertEqual(parsed["version"], "v2.9.0")

    def test_text_summary_output_is_human_readable(self):
        summary = deploy.build_rollback_summary("market", "development", "dev-42")
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            deploy.print_rollback_summary(summary, "text")

        output = stdout.getvalue()
        self.assertIn("Rollback dry-run summary", output)
        self.assertIn("Service:     market", output)
        self.assertIn("Planned actions:", output)
        self.assertIn("Rollback steps:", output)

    def test_secret_like_values_are_redacted(self):
        payload = {
            "api_key": "abc123",
            "note": "bearer=top-secret-token",
            "nested": {"password": "hunter2"},
        }

        redacted = deploy.redact_value("", payload)

        self.assertEqual(redacted["api_key"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["password"], "[REDACTED]")
        self.assertIn("bearer=[REDACTED]", redacted["note"])
        self.assertNotIn("top-secret-token", redacted["note"])


if __name__ == "__main__":
    unittest.main()
