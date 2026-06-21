#!/usr/bin/env python3
"""Regression tests for bounty issue body validation."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import validate_bounty_issue

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "bounty_issue"
SCRIPT = Path(__file__).resolve().parent / "validate_bounty_issue.py"


class BountyIssueValidationTests(unittest.TestCase):
    def test_valid_fixture_passes(self) -> None:
        result = validate_bounty_issue.validate_path(FIXTURE_DIR / "valid.md")

        self.assertTrue(result.ok, result.errors)

    def test_missing_commissions_fails(self) -> None:
        result = validate_bounty_issue.validate_path(FIXTURE_DIR / "invalid_missing_commissions.md")

        self.assertFalse(result.ok)
        self.assertIn("missing required section: Commissions:", result.errors)

    def test_changed_commissions_text_fails(self) -> None:
        result = validate_bounty_issue.validate_path(FIXTURE_DIR / "invalid_commissions_text.md")

        self.assertFalse(result.ok)
        self.assertIn("commissions paragraph does not match the required text exactly", result.errors)

    def test_stub_diagnostic_without_exclusion_fails(self) -> None:
        result = validate_bounty_issue.validate_path(FIXTURE_DIR / "invalid_stub_diagnostic.md")

        self.assertFalse(result.ok)
        self.assertIn("required validation must explicitly exclude build-00000000 diagnostics", result.errors)

    def test_json_cli_reports_per_file_results(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--json",
                str(FIXTURE_DIR / "valid.md"),
                str(FIXTURE_DIR / "invalid_missing_commissions.md"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual([item["ok"] for item in payload], [True, False])


if __name__ == "__main__":
    unittest.main()
