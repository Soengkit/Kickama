import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.log_aggregator import LogAggregator


class LogAggregatorJsonlTest(unittest.TestCase):
    def test_jsonl_export_orders_timestamped_records_and_emits_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            json_log = temp_path / "app.log"
            nginx_log = temp_path / "nginx.log"
            output = temp_path / "report.jsonl"

            json_log.write_text(
                '{"timestamp":"2026-06-19T12:01:00+00:00","level":"ERROR","service":"api","message":"late json error","request_id":"req-1"}\n\n',
                encoding="utf-8",
            )
            nginx_log.write_text(
                '127.0.0.1 - - [19/Jun/2026:12:00:00 +0000] "GET /health HTTP/1.1" 200 12 "-" "curl"\n',
                encoding="utf-8",
            )

            aggregator = LogAggregator()
            aggregator.process_file(str(json_log))
            aggregator.process_file(str(nginx_log))
            aggregator.export_jsonl(str(output))

            records = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(
                [record["message"] for record in records],
                ["GET /health HTTP/1.1", "late json error", "Unparsed log line"],
            )
            self.assertEqual(
                set(records[0].keys()),
                {"timestamp", "level", "source", "message", "metadata"},
            )
            self.assertEqual(records[0]["metadata"]["format"], "nginx")
            self.assertEqual(records[1]["level"], "error")
            self.assertEqual(records[1]["metadata"]["request_id"], "req-1")
            self.assertEqual(records[2]["level"], "warning")
            self.assertEqual(records[2]["metadata"]["line_number"], 2)
            self.assertEqual(records[2]["metadata"]["raw"], "")


if __name__ == "__main__":
    unittest.main()
