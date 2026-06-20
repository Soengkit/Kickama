import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.log_aggregator import (  # noqa: E402
    JSONLogParser,
    LogAggregator,
    NginxLogParser,
    TextLogParser,
)


def utc_timestamp(value: str, fmt: str) -> int:
    return int(datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).timestamp())


class JSONLogParserTests(unittest.TestCase):
    def test_parses_structured_json_aliases(self):
        parsed = JSONLogParser().parse(
            '{"time": 1717245296, "severity": "ERROR", "logger": "orders", '
            '"msg": "matching engine rejected order", "order_id": "ord_42"}'
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["timestamp"], 1717245296)
        self.assertEqual(parsed["level"], "ERROR")
        self.assertEqual(parsed["service"], "orders")
        self.assertEqual(parsed["message"], "matching engine rejected order")
        self.assertEqual(parsed["fields"]["order_id"], "ord_42")
        self.assertEqual(parsed["format"], "json")

    def test_rejects_malformed_and_non_object_json(self):
        parser = JSONLogParser()

        self.assertIsNone(parser.parse('{"timestamp": 1717245296, "level": "info"'))
        self.assertIsNone(parser.parse('["timestamp", "level", "message"]'))


class TextLogParserTests(unittest.TestCase):
    def test_parses_plain_text_timestamp_level_and_service(self):
        parsed = TextLogParser().parse(
            "2024-06-01 12:34:56 [payments] WARN retrying settlement job"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["timestamp"], utc_timestamp("2024-06-01 12:34:56", "%Y-%m-%d %H:%M:%S"))
        self.assertEqual(parsed["level"], "warn")
        self.assertEqual(parsed["service"], "payments")
        self.assertEqual(parsed["message"], "2024-06-01 12:34:56 [payments] WARN retrying settlement job")
        self.assertEqual(parsed["format"], "text")

    def test_handles_empty_lines_unknown_severity_and_invalid_dates(self):
        parser = TextLogParser()

        self.assertIsNone(parser.parse("   \n"))

        parsed = parser.parse("2024-02-30 08:00:00 worker completed heartbeat")
        self.assertIsNotNone(parsed)
        self.assertIsNone(parsed["timestamp"])
        self.assertEqual(parsed["level"], "unknown")
        self.assertIsNone(parsed["service"])

    def test_documents_syslog_year_limitation(self):
        parsed = TextLogParser().parse("Jun  1 12:00:00 GATEWAY: accepted legacy event")

        self.assertIsNotNone(parsed)
        # Syslog-style lines do not include a year; the legacy parser keeps
        # Python's strptime default year instead of inferring the current year.
        self.assertEqual(
            parsed["timestamp"],
            utc_timestamp("Jun  1 12:00:00", "%b %d %H:%M:%S"),
        )
        self.assertEqual(parsed["level"], "unknown")
        # The current service extractor sees the timestamp's numeric segment
        # before the syslog tag, so syslog tag inference remains unsupported.
        self.assertIsNone(parsed["service"])


class NginxLogParserTests(unittest.TestCase):
    def test_parses_successful_access_log_fields(self):
        line = (
            '203.0.113.7 - alice [01/Jun/2024:12:34:56 +0000] '
            '"GET /api/orders HTTP/1.1" 200 512 "https://example.test/app" "curl/8.0"'
        )

        parsed = NginxLogParser().parse(line)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["timestamp"], utc_timestamp("01/Jun/2024:12:34:56 +0000", "%d/%b/%Y:%H:%M:%S %z"))
        self.assertEqual(parsed["level"], "info")
        self.assertEqual(parsed["service"], "nginx")
        self.assertEqual(parsed["message"], "GET /api/orders HTTP/1.1")
        self.assertEqual(parsed["fields"]["remote_addr"], "203.0.113.7")
        self.assertEqual(parsed["fields"]["remote_user"], "alice")
        self.assertEqual(parsed["fields"]["status"], 200)
        self.assertEqual(parsed["fields"]["body_bytes"], "512")
        self.assertEqual(parsed["fields"]["referer"], "https://example.test/app")
        self.assertEqual(parsed["fields"]["user_agent"], "curl/8.0")
        self.assertEqual(parsed["format"], "nginx")

    def test_classifies_http_4xx_and_5xx(self):
        parser = NginxLogParser()

        not_found = parser.parse(
            '198.51.100.9 - - [01/Jun/2024:12:35:00 +0000] '
            '"GET /missing HTTP/1.1" 404 128 "-" "Mozilla/5.0"'
        )
        server_error = parser.parse(
            '198.51.100.10 - - [01/Jun/2024:12:36:00 +0000] '
            '"POST /trade HTTP/1.1" 503 64 "-" "synthetic-monitor"'
        )

        self.assertEqual(not_found["level"], "warn")
        self.assertEqual(not_found["fields"]["status"], 404)
        self.assertEqual(server_error["level"], "error")
        self.assertEqual(server_error["fields"]["status"], 503)

    def test_rejects_malformed_nginx_lines(self):
        self.assertIsNone(NginxLogParser().parse('203.0.113.7 "GET /unterminated 200'))


class LogAggregatorParserOrderTests(unittest.TestCase):
    def test_nginx_parser_runs_before_text_fallback(self):
        aggregator = LogAggregator()
        parsed = aggregator._parse_line(
            '198.51.100.10 - - [01/Jun/2024:12:36:00 +0000] '
            '"POST /trade HTTP/1.1" 503 64 "-" "synthetic-monitor"'
        )

        self.assertTrue(parsed)
        self.assertEqual(len(aggregator.entries), 1)
        entry = aggregator.entries[0]
        self.assertEqual(entry["format"], "nginx")
        self.assertEqual(entry["service"], "nginx")
        self.assertEqual(entry["level"], "error")
        self.assertEqual(aggregator.level_counts["error"], 1)
        self.assertEqual(aggregator.service_counts["nginx"], 1)
        self.assertEqual(aggregator.errors_by_service["nginx"], ["POST /trade HTTP/1.1"])


if __name__ == "__main__":
    unittest.main()
