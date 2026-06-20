import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.ai_pipeline_timing_summary import (  # noqa: E402
    StageTiming,
    build_timing_summary,
    format_timing_summary,
    main,
    sanitize_for_summary,
)


class AIPipelineTimingSummaryTests(unittest.TestCase):
    def test_summary_marks_slowest_and_over_budget_stage(self):
        summary = build_timing_summary(
            [
                StageTiming("data_preparation", 1.25),
                StageTiming("backend_training", 3.5),
                StageTiming("evaluation", 0.75),
            ],
            budget_seconds=2,
            slowest_count=1,
        )

        self.assertEqual(summary["total_duration_seconds"], 5.5)
        self.assertEqual(summary["over_budget_count"], 1)
        self.assertEqual(summary["slowest_stages"][0]["name"], "backend_training")
        self.assertEqual(summary["over_budget_stages"][0]["name"], "backend_training")


    def test_short_text_summary_includes_budget_and_stage_status(self):
        summary = build_timing_summary(
            [StageTiming("deploy", 2.25, status="failed")],
            budget_seconds=1,
        )
        text = format_timing_summary(summary)

        self.assertIn("AI Pipeline Timing Budget Summary", text)
        self.assertIn("deploy: 2.250s status=failed over_budget", text)
        self.assertIn("total_duration_seconds: 2.250", text)


    def test_secret_like_metadata_is_redacted_before_summary_output(self):
        summary = build_timing_summary(
            [
                StageTiming(
                    "tools_training",
                    0.5,
                    metadata={
                        "prompt": "raw user prompt",
                        "safe_note": "authorization: Bearer abc123 should not leak",
                        "nested": {"api_key": "sk-live"},
                    },
                )
            ]
        )
        rendered = json.dumps(summary)

        self.assertNotIn("raw user prompt", rendered)
        self.assertNotIn("sk-live", rendered)
        self.assertNotIn("abc123", rendered)
        self.assertGreaterEqual(rendered.count("[REDACTED]"), 3)


    def test_sanitize_preserves_non_secret_values(self):
        self.assertEqual(
            sanitize_for_summary({"stage": "train", "elapsed": 1.2}),
            {
                "stage": "train",
                "elapsed": 1.2,
            },
        )


    def test_cli_writes_json_and_text_outputs(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            output_json = Path(raw_dir) / "summary.json"
            output_text = Path(raw_dir) / "summary.txt"
            original_argv = sys.argv[:]
            sys.argv = [
                "ai_pipeline_timing_summary.py",
                "--stage",
                "train:4.2:ok",
                "--budget-seconds",
                "3",
                "--output-json",
                str(output_json),
                "--output-text",
                str(output_text),
            ]
            try:
                self.assertEqual(main(), 0)
            finally:
                sys.argv = original_argv

            data = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(data["over_budget_count"], 1)
            self.assertIn(
                "train: 4.200s status=ok over_budget",
                output_text.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
