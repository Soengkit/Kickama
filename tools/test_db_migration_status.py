#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "db_migration.py"
SPEC = importlib.util.spec_from_file_location("db_migration", MODULE_PATH)
db_migration = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(db_migration)


class MigrationStatusTest(unittest.TestCase):
    def test_clean_status_has_no_pending_or_missing_versions(self):
        migrations = [
            {"version": "20240101000000", "description": "Initial", "type": "sql", "applied": True},
            {"version": "20240102000000", "description": "Add users", "type": "py", "applied": True},
        ]

        report = db_migration.build_status_report(
            migrations=migrations,
            migration_files=[],
            state_source="fixture",
        )

        self.assertTrue(report["consistent"])
        self.assertEqual(report["summary"], {"applied": 2, "pending": 0, "missing_on_disk": 0})
        self.assertEqual([row["version"] for row in report["applied"]], ["20240101000000", "20240102000000"])
        self.assertEqual(report["pending"], [])
        self.assertEqual(report["missing_on_disk"], [])

    def test_pending_status_lists_unapplied_migrations_in_version_order(self):
        migrations = [
            {"version": "20240102000000", "description": "Add users", "type": "sql", "applied": False},
            {"version": "20240101000000", "description": "Initial", "type": "sql", "applied": True},
        ]

        report = db_migration.build_status_report(
            migrations=migrations,
            migration_files=[],
            state_source="fixture",
        )

        self.assertTrue(report["consistent"])
        self.assertEqual(report["summary"], {"applied": 1, "pending": 1, "missing_on_disk": 0})
        self.assertEqual([row["version"] for row in report["applied"]], ["20240101000000"])
        self.assertEqual([row["version"] for row in report["pending"]], ["20240102000000"])

    def test_inconsistent_state_lists_applied_version_missing_from_repo(self):
        migrations = [
            {"version": "20240101000000", "description": "Initial", "type": "sql", "applied": False},
        ]

        report = db_migration.build_status_report(
            applied_versions=["20240101000000", "20990101000000"],
            migrations=migrations,
            migration_files=[],
            state_source="fixture",
        )

        self.assertFalse(report["consistent"])
        self.assertEqual(report["summary"], {"applied": 1, "pending": 0, "missing_on_disk": 1})
        self.assertEqual(report["missing_on_disk"][0]["version"], "20990101000000")
        self.assertEqual(report["missing_on_disk"][0]["state"], "missing_on_disk")

    def test_discovers_migration_files_and_ignores_unrelated_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations_dir = Path(tmpdir) / "migrations"
            migrations_dir.mkdir()
            (migrations_dir / "20240103040506_add_accounts.sql").write_text("-- up\n", encoding="utf-8")
            (migrations_dir / "20240103040507_backfill_accounts.py").write_text("# up\n", encoding="utf-8")
            (migrations_dir / "README.md").write_text("ignore me\n", encoding="utf-8")

            discovered = db_migration.discover_migration_files(str(migrations_dir))

        self.assertEqual(
            [(row["version"], row["description"], row["type"]) for row in discovered],
            [
                ("20240103040506", "add accounts", "sql"),
                ("20240103040507", "backfill accounts", "py"),
            ],
        )

    def test_json_output_is_parseable_and_deterministically_sorted(self):
        report = db_migration.build_status_report(
            applied_versions=["20240102000000"],
            migrations=[
                {"version": "20240102000000", "description": "Second", "type": "sql", "applied": False},
                {"version": "20240101000000", "description": "First", "type": "sql", "applied": False},
            ],
            migration_files=[],
            state_source="fixture",
        )
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            db_migration.print_status_report(report, json_output=True)

        decoded = json.loads(stdout.getvalue())
        self.assertEqual([row["version"] for row in decoded["applied"]], ["20240102000000"])
        self.assertEqual([row["version"] for row in decoded["pending"]], ["20240101000000"])
        self.assertIn('"applied"', stdout.getvalue().splitlines()[0])

    def test_status_subcommand_supports_json_output(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            rc = db_migration.main(["status", "--json"])

        self.assertEqual(rc, 0)
        decoded = json.loads(stdout.getvalue())
        self.assertTrue(decoded["consistent"])
        self.assertIn("summary", decoded)

    def test_status_subcommand_returns_nonzero_for_inconsistent_state(self):
        original_fetch = db_migration.fetch_applied_versions
        original_status = db_migration.get_migration_status
        db_migration.fetch_applied_versions = lambda: ["20990101000000"]
        db_migration.get_migration_status = lambda: []
        stdout = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout):
                rc = db_migration.main(["status", "--json"])
        finally:
            db_migration.fetch_applied_versions = original_fetch
            db_migration.get_migration_status = original_status

        decoded = json.loads(stdout.getvalue())
        self.assertEqual(rc, 1)
        self.assertFalse(decoded["consistent"])
        self.assertEqual(decoded["summary"]["missing_on_disk"], 1)


if __name__ == "__main__":
    unittest.main()
