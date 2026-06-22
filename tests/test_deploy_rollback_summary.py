"""
Tests for deploy dry-run rollback summary export (bounty #1 on Soengkit/zeroeye).

Covers summary generation, text/JSON formatting, file export, and the
required summary fields (service, environment, version, planned actions,
risk notes, rollback steps, filtering by service/environment).
"""

import sys
import json
import os
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from deploy import (
    generate_rollback_summary,
    format_rollback_summary_text,
    export_rollback_summary,
    SERVICES,
    ENVIRONMENTS,
)


class TestGenerateRollbackSummary(unittest.TestCase):
    def test_contains_required_fields(self):
        summary = generate_rollback_summary("backend", "production", "v1.2.3")
        for field in ("service", "environment", "version", "planned_actions",
                       "risk_notes", "rollback_steps", "generated_at", "namespace"):
            self.assertIn(field, summary)

    def test_service_and_env_values(self):
        summary = generate_rollback_summary("frontend", "staging", "v2.0")
        self.assertEqual(summary["service"], "frontend")
        self.assertEqual(summary["environment"], "staging")
        self.assertEqual(summary["version"], "v2.0")

    def test_defaults_empty_lists(self):
        summary = generate_rollback_summary("backend", "production", "v1")
        self.assertEqual(summary["planned_actions"], [])
        self.assertEqual(summary["risk_notes"], [])
        self.assertEqual(summary["rollback_steps"], [])

    def test_custom_actions_risk_steps(self):
        summary = generate_rollback_summary(
            "backend", "production", "v1",
            planned_actions=["rollback", "health check"],
            risk_notes=["schema mismatch risk"],
            rollback_steps=["step1", "step2"],
        )
        self.assertEqual(summary["planned_actions"], ["rollback", "health check"])
        self.assertEqual(summary["risk_notes"], ["schema mismatch risk"])
        self.assertEqual(summary["rollback_steps"], ["step1", "step2"])

    def test_namespace_from_environment(self):
        summary = generate_rollback_summary("backend", "production", "v1")
        self.assertEqual(summary["namespace"], ENVIRONMENTS["production"]["namespace"])

    def test_service_name_lookup(self):
        summary = generate_rollback_summary("backend", "production", "v1")
        self.assertEqual(summary["service_name"], SERVICES["backend"]["name"])


class TestFormatSummaryText(unittest.TestCase):
    def test_text_contains_sections(self):
        summary = generate_rollback_summary(
            "backend", "production", "v1.2.3",
            planned_actions=["rollback"],
            risk_notes=["risk"],
            rollback_steps=["step1"],
        )
        text = format_rollback_summary_text(summary)
        self.assertIn("Dry-Run Rollback Summary", text)
        self.assertIn("Service:", text)
        self.assertIn("Environment:", text)
        self.assertIn("Version/Tag:", text)
        self.assertIn("Planned actions:", text)
        self.assertIn("- rollback", text)
        self.assertIn("Risk notes:", text)
        self.assertIn("! risk", text)
        self.assertIn("Rollback steps:", text)
        self.assertIn("1. step1", text)

    def test_text_handles_empty_lists(self):
        summary = generate_rollback_summary("backend", "production", "v1")
        text = format_rollback_summary_text(summary)
        self.assertIn("(none)", text)


class TestExportSummary(unittest.TestCase):
    def test_export_text(self):
        summary = generate_rollback_summary("backend", "production", "v1")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            export_rollback_summary(summary, path, "text")
            content = open(path).read()
            self.assertIn("Dry-Run Rollback Summary", content)
        finally:
            os.unlink(path)

    def test_export_json(self):
        summary = generate_rollback_summary(
            "frontend", "staging", "v2.0",
            planned_actions=["deploy"],
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            export_rollback_summary(summary, path, "json")
            data = json.load(open(path))
            self.assertEqual(data["service"], "frontend")
            self.assertEqual(data["environment"], "staging")
            self.assertEqual(data["planned_actions"], ["deploy"])
        finally:
            os.unlink(path)


class TestFiltering(unittest.TestCase):
    def test_summary_for_each_service(self):
        for svc in SERVICES:
            summary = generate_rollback_summary(svc, "production", "v1")
            self.assertEqual(summary["service"], svc)

    def test_summary_for_each_environment(self):
        for env in ENVIRONMENTS:
            summary = generate_rollback_summary("backend", env, "v1")
            self.assertEqual(summary["environment"], env)
            self.assertEqual(summary["namespace"], ENVIRONMENTS[env]["namespace"])


if __name__ == "__main__":
    unittest.main()
