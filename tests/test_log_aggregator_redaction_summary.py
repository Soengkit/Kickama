import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from log_aggregator import LogAggregator, redact_secret_value  # noqa: E402


class LogAggregatorRedactionSummaryTests(unittest.TestCase):
    def test_redaction_summary_counts_valid_malformed_and_secret_fields(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            log_path = Path(raw_dir) / "app.log"
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp": "2026-06-20T12:00:00",
                                "level": "INFO",
                                "service": "api",
                                "message": "started",
                                "token": "secret-token",
                            }
                        ),
                        "",
                        "2026-06-20 12:01:00 ERROR [worker] password=hunter2 failed",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            aggregator = LogAggregator()
            self.assertEqual(aggregator.process_file(str(log_path)), 2)
            summary = aggregator.get_redaction_summary()

            self.assertEqual(summary["processed_lines"], 3)
            self.assertEqual(summary["parsed_entries"], 2)
            self.assertEqual(summary["malformed_lines"], 1)
            self.assertGreaterEqual(summary["redacted_fields"], 2)
            self.assertEqual(summary["by_file"][0]["source_file"], "app.log")

            rendered = json.dumps(aggregator.entries)
            self.assertNotIn("secret-token", rendered)
            self.assertNotIn("hunter2", rendered)

    def test_text_and_json_redaction_summary_exports(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            raw_path = Path(raw_dir)
            log_path = raw_path / "service.log"
            json_summary = raw_path / "summary.json"
            text_summary = raw_path / "summary.txt"
            log_path.write_text(
                '{"level":"WARN","service":"svc","message":"authorization: Bearer abc123"}\n',
                encoding="utf-8",
            )

            aggregator = LogAggregator()
            aggregator.process_file(str(log_path))
            aggregator.export_redaction_summary(str(json_summary), "json")
            aggregator.export_redaction_summary(str(text_summary), "text")

            data = json.loads(json_summary.read_text(encoding="utf-8"))
            self.assertEqual(data["redacted_fields"], 2)
            self.assertIn("Log Redaction Summary", text_summary.read_text(encoding="utf-8"))

    def test_redact_secret_value_preserves_safe_fields(self):
        redacted, count = redact_secret_value({"service": "api", "message": "ok"})
        self.assertEqual(count, 0)
        self.assertEqual(redacted, {"service": "api", "message": "ok"})


if __name__ == "__main__":
    unittest.main()
