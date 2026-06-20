#!/usr/bin/env python3
import contextlib
import io
import importlib.util
import pathlib
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer


MODULE_PATH = pathlib.Path(__file__).with_name("health_check.py")
SPEC = importlib.util.spec_from_file_location("health_check", MODULE_PATH)
health_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(health_check)


class HealthHandler(BaseHTTPRequestHandler):
    response_code = 200

    def do_GET(self):
        self.send_response(self.response_code)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args):
        return


@contextlib.contextmanager
def health_server(status_code):
    handler = type("Handler", (HealthHandler,), {"response_code": status_code})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@contextlib.contextmanager
def patched_health_targets(service_name, port):
    old_services = health_check.SERVICES
    old_infra = health_check.INFRASTRUCTURE
    health_check.SERVICES = {
        service_name: {
            "host": "127.0.0.1",
            "port": port,
            "path": "/health",
            "timeout": 2,
        }
    }
    health_check.INFRASTRUCTURE = {}
    try:
        yield
    finally:
        health_check.SERVICES = old_services
        health_check.INFRASTRUCTURE = old_infra


class PrometheusHealthCheckTest(unittest.TestCase):
    def test_prometheus_output_for_healthy_service(self):
        with health_server(200) as port:
            with patched_health_targets('backend"blue', port):
                results = health_check.run_health_checks("backend\"blue")
                output = health_check.format_prometheus(results)

        self.assertEqual(results["services"]['backend"blue']["code"], 200)
        self.assertIn('tent_health_service_up{service="backend\\"blue"', output)
        self.assertIn('tent_health_service_up{service="backend\\"blue",endpoint=', output)
        self.assertIn("} 1\n", output)
        self.assertIn("tent_health_service_latency_ms", output)
        self.assertIn("tent_health_service_http_status_code", output)
        self.assertIn("tent_health_service_check_timestamp_seconds", output)

    def test_prometheus_output_for_unhealthy_service(self):
        with health_server(503) as port:
            with patched_health_targets("market", port):
                results = health_check.run_health_checks("market")
                output = health_check.format_prometheus(results)

        self.assertEqual(results["overall_status"], "DEGRADED")
        self.assertEqual(results["services"]["market"]["code"], 503)
        self.assertIn('tent_health_service_up{service="market"', output)
        self.assertIn('tent_health_service_http_status_code{service="market"', output)
        self.assertIn("} 0\n", output)
        self.assertIn("} 503\n", output)

    def test_main_returns_nonzero_for_failed_prometheus_checks(self):
        class Args:
            service = "market"
            format = "prometheus"
            json = False
            watch = False
            interval = 30
            output = None

        old_parse_args = health_check.parse_args
        health_check.parse_args = lambda: Args()
        try:
            with health_server(503) as port:
                with patched_health_targets("market", port):
                    with contextlib.redirect_stdout(io.StringIO()) as stdout:
                        exit_code = health_check.main()
            self.assertEqual(exit_code, 1)
            self.assertIn("tent_health_service_up", stdout.getvalue())
        finally:
            health_check.parse_args = old_parse_args


if __name__ == "__main__":
    unittest.main()
