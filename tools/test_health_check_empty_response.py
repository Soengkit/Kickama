#!/usr/bin/env python3
import json
import os
import sys
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(__file__))

from health_check import check_http_service


def make_health_handler(status_code, body, content_type="application/json"):
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status_code)
            if content_type is not None:
                self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return HealthHandler


@contextmanager
def mock_health_server(status_code, body, content_type="application/json"):
    server = HTTPServer(
        ("127.0.0.1", 0),
        make_health_handler(status_code, body, content_type),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


class HealthCheckEmptyResponseTest(unittest.TestCase):
    def assert_health_result(self, status_code, body, want_status, want_detail, content_type="application/json"):
        with mock_health_server(status_code, body, content_type) as port:
            status, detail, code = check_http_service("127.0.0.1", port, "/health", 2)

        self.assertEqual(code, status_code)
        self.assertEqual(status, want_status)
        self.assertIn(want_detail, detail)

    def test_empty_200_is_critical(self):
        self.assert_health_result(200, b"", "CRITICAL", "empty response body")

    def test_malformed_json_is_critical(self):
        self.assert_health_result(200, b"{not-json", "CRITICAL", "invalid JSON")

    def test_unexpected_content_type_is_critical(self):
        self.assert_health_result(200, b'{"status": "ok"}', "CRITICAL", "unexpected content type", "text/plain")

    def test_valid_healthy_json_is_ok(self):
        payload = json.dumps({"status": "ok", "version": "test"}).encode("utf-8")
        self.assert_health_result(200, payload, "OK", "health status ok")

    def test_http_failure_is_critical(self):
        self.assert_health_result(503, b"maintenance", "CRITICAL", "HTTP 503")


if __name__ == "__main__":
    unittest.main()
