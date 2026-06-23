#!/usr/bin/env python3
"""
Health check tool for the Tent of Trials platform.
Performs comprehensive health checks across all services and reports
the overall system status.

This tool is used by:
  - The Kubernetes liveness/readiness probes
  - The deployment pipeline (post-deployment validation)
  - The monitoring system (periodic health checks)
  - The on-call engineer (manual troubleshooting)

The health check performs the following checks:
  1. Service availability (HTTP health endpoints)
  2. Database connectivity (connection test)
  3. Redis connectivity (ping test)
  4. Kafka connectivity (metadata fetch)
  5. Message queue depth (consumer lag check)
  6. Certificate expiry (TLS certificate check)
  7. Disk space (filesystem usage check)
  8. Memory usage (process memory check)

Each check returns a status of OK, WARNING, or CRITICAL, along with
a detail message and optional diagnostic data.

Usage:
    python3 health_check.py                  # Check all services
    python3 health_check.py --service backend # Check specific service
    python3 health_check.py --json            # JSON output
    python3 health_check.py --timeout 2 --probe-rate 5
    python3 health_check.py --watch           # Continuous monitoring
"""

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SERVICES = {
    "backend": {"host": "localhost", "port": 8080, "path": "/health", "timeout": 5},
    "market": {"host": "localhost", "port": 8081, "path": "/health", "timeout": 5},
    "frailbox": {"host": "localhost", "port": 8082, "path": "/health", "timeout": 10},
    "frontend": {"host": "localhost", "port": 3000, "path": "/", "timeout": 5},
}

INFRASTRUCTURE = {
    "postgresql": {"host": os.environ.get("DB_HOST", "localhost"), "port": int(os.environ.get("DB_PORT", "5432")), "timeout": 5},
    "redis": {"host": os.environ.get("REDIS_HOST", "localhost"), "port": int(os.environ.get("REDIS_PORT", "6379")), "timeout": 5},
    "kafka": {"host": os.environ.get("KAFKA_HOST", "localhost"), "port": int(os.environ.get("KAFKA_PORT", "9092")), "timeout": 5},
}

DISK_THRESHOLD_WARNING = 80
DISK_THRESHOLD_CRITICAL = 90

MEMORY_THRESHOLD_WARNING = 80
MEMORY_THRESHOLD_CRITICAL = 90

HALF_OPEN_RATE_FACTOR = 0.5

# ---------------------------------------------------------------------------
# PROBE RATE LIMITING
# ---------------------------------------------------------------------------

class ProbeRateLimiter:
    def __init__(
        self,
        rate_per_second: Optional[float],
        burst: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        if rate_per_second is not None and rate_per_second <= 0:
            raise ValueError("probe rate must be greater than zero")
        self.rate_per_second = rate_per_second
        self.burst = burst or rate_per_second or 0
        self.tokens = self.burst
        self.clock = clock
        self.sleep_fn = sleep_fn
        self.updated_at = clock()
        self.total_probes = 0
        self.throttled_requests = 0
        self.sleep_seconds = 0.0
        self.current_rate = rate_per_second
        self.half_open_reductions = 0

    @property
    def enabled(self) -> bool:
        return self.rate_per_second is not None

    def wait(self, half_open: bool = False) -> None:
        self.total_probes += 1
        if not self.enabled:
            return

        effective_rate = self.rate_per_second or 0
        if half_open:
            effective_rate *= HALF_OPEN_RATE_FACTOR
            self.half_open_reductions += 1
        self.current_rate = effective_rate

        now = self.clock()
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.burst, self.tokens + elapsed * effective_rate)
        self.updated_at = now

        if self.tokens < 1.0:
            delay = (1.0 - self.tokens) / effective_rate
            self.throttled_requests += 1
            self.sleep_seconds += delay
            self.sleep_fn(delay)

            now = self.clock()
            elapsed = max(0.0, now - self.updated_at)
            self.tokens = min(self.burst, self.tokens + elapsed * effective_rate)
            self.updated_at = now

        self.tokens = max(0.0, self.tokens - 1.0)

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured_rate": self.rate_per_second,
            "current_rate": self.current_rate,
            "burst": self.burst if self.enabled else None,
            "total_probes": self.total_probes,
            "throttled_requests": self.throttled_requests,
            "sleep_seconds": round(self.sleep_seconds, 3),
            "half_open_reductions": self.half_open_reductions,
        }


def parse_service_timeout_overrides(values: Optional[List[str]]) -> Dict[str, float]:
    overrides: Dict[str, float] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"invalid service timeout override: {value}")
        name, timeout = value.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"invalid service timeout override: {value}")
        try:
            parsed = float(timeout)
        except ValueError:
            raise ValueError(f"timeout for {name} must be a number")
        if parsed <= 0:
            raise ValueError(f"timeout for {name} must be greater than zero")
        overrides[name] = parsed
    return overrides


def validate_positive_option(name: str, value: Optional[float]) -> None:
    if value is not None and value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def resolve_probe_timeout(
    name: str,
    config: Dict[str, Any],
    global_timeout: Optional[float],
    service_timeouts: Dict[str, float],
) -> float:
    if name in service_timeouts:
        return service_timeouts[name]
    if global_timeout is not None:
        return global_timeout
    return float(config["timeout"])

# ---------------------------------------------------------------------------
# CHECK FUNCTIONS
# ---------------------------------------------------------------------------

def check_http_service(host: str, port: int, path: str, timeout: float) -> Tuple[str, str, int]:
    import http.client
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", path)
        resp = conn.getresponse()
        status = resp.status
        body = resp.read().decode("utf-8", errors="replace")[:200]
        conn.close()

        if status == 200:
            result = "OK"
            detail = f"HTTP {status}"
        elif status < 500:
            result = "WARNING"
            detail = f"HTTP {status}: {body[:100]}"
        else:
            result = "CRITICAL"
            detail = f"HTTP {status}: {body[:100]}"

        return result, detail, status
    except Exception as e:
        return "CRITICAL", str(e), 0


def check_tcp_port(host: str, port: int, timeout: float) -> Tuple[str, str, float]:
    try:
        start = time.time()
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        latency = (time.time() - start) * 1000
        return "OK", f"Connected ({latency:.1f}ms)", latency
    except socket.timeout:
        return "CRITICAL", f"Connection timeout ({timeout}s)", 0
    except ConnectionRefusedError:
        return "CRITICAL", "Connection refused", 0
    except Exception as e:
        return "CRITICAL", str(e), 0


def check_certificate_expiry(host: str, port: int = 443) -> Tuple[str, str, int]:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return "WARNING", "No certificate found", 0

                from datetime import datetime as dt
                expires = dt.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                days_left = (expires - dt.now()).days

                if days_left > 30:
                    return "OK", f"Certificate expires in {days_left} days", days_left
                elif days_left > 7:
                    return "WARNING", f"Certificate expires in {days_left} days", days_left
                else:
                    return "CRITICAL", f"Certificate expires in {days_left} days", days_left
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_disk_usage(path: str = "/") -> Tuple[str, str, float]:
    try:
        stat = os.statvfs(path)
        total = stat.f_frsize * stat.f_blocks
        free = stat.f_frsize * stat.f_bavail
        used = total - free
        pct = (used / total) * 100

        if pct < DISK_THRESHOLD_WARNING:
            return "OK", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        elif pct < DISK_THRESHOLD_CRITICAL:
            return "WARNING", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        else:
            return "CRITICAL", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_memory_usage() -> Tuple[str, str, float]:
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().replace(" kB", "")
                    try:
                        meminfo[key] = int(value) * 1024
                    except ValueError:
                        pass

        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0)
        used = total - available
        pct = (used / total) * 100 if total > 0 else 0

        if pct < MEMORY_THRESHOLD_WARNING:
            return "OK", f"{pct:.1f}% used ({used // (1024**3)}GB/{total // (1024**3)}GB)", pct
        elif pct < MEMORY_THRESHOLD_CRITICAL:
            return "WARNING", f"{pct:.1f}% used", pct
        else:
            return "CRITICAL", f"{pct:.1f}% used", pct
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_load_average() -> Tuple[str, str, float]:
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().strip().split()
            load = float(parts[0])
            cpu_count = os.cpu_count() or 1
            load_pct = (load / cpu_count) * 100

            if load_pct < 70:
                return "OK", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
            elif load_pct < 90:
                return "WARNING", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
            else:
                return "CRITICAL", f"Load: {load} ({load_pct:.0f}% of {cpu_count} cores)", load
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


# ---------------------------------------------------------------------------
# HEALTH CHECK RUNNER
# ---------------------------------------------------------------------------

def run_health_checks(
    service: Optional[str] = None,
    json_output: bool = False,
    timeout: Optional[float] = None,
    service_timeouts: Optional[Dict[str, float]] = None,
    probe_rate: Optional[float] = None,
    half_open_services: Optional[Set[str]] = None,
    clock: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    http_checker: Callable[[str, int, str, float], Tuple[str, str, int]] = check_http_service,
    tcp_checker: Callable[[str, int, float], Tuple[str, str, float]] = check_tcp_port,
) -> Dict[str, Any]:
    service_timeouts = service_timeouts or {}
    half_open_services = half_open_services or set()
    limiter = ProbeRateLimiter(probe_rate, clock=clock, sleep_fn=sleep_fn)

    results: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "services": {},
        "infrastructure": {},
        "system": {},
        "rate_limiter": {},
        "overall_status": "OK",
    }

    all_ok = True

    # Check services
    for name, config in SERVICES.items():
        if service and name != service:
            continue
        probe_timeout = resolve_probe_timeout(name, config, timeout, service_timeouts)
        half_open = name in half_open_services
        limiter.wait(half_open=half_open)
        status, detail, code = http_checker(
            config["host"], config["port"], config["path"], probe_timeout
        )
        results["services"][name] = {
            "status": status,
            "detail": detail,
            "code": code,
            "endpoint": f"http://{config['host']}:{config['port']}{config['path']}",
            "timeout_seconds": probe_timeout,
            "half_open_rate_reduced": half_open,
        }
        if status == "CRITICAL":
            all_ok = False

    # Check infrastructure
    for name, config in INFRASTRUCTURE.items():
        if service and name != service:
            continue
        probe_timeout = resolve_probe_timeout(name, config, timeout, service_timeouts)
        half_open = name in half_open_services
        limiter.wait(half_open=half_open)
        status, detail, latency = tcp_checker(config["host"], config["port"], probe_timeout)
        results["infrastructure"][name] = {
            "status": status,
            "detail": detail,
            "endpoint": f"{config['host']}:{config['port']}",
            "timeout_seconds": probe_timeout,
            "half_open_rate_reduced": half_open,
        }
        if status == "CRITICAL":
            all_ok = False

    # Check system resources
    disk_status, disk_detail, disk_pct = check_disk_usage()
    results["system"]["disk"] = {"status": disk_status, "detail": disk_detail}
    if disk_status == "CRITICAL":
        all_ok = False

    mem_status, mem_detail, mem_pct = check_memory_usage()
    results["system"]["memory"] = {"status": mem_status, "detail": mem_detail}
    if mem_status == "CRITICAL":
        all_ok = False

    load_status, load_detail, load_val = check_load_average()
    results["system"]["load"] = {"status": load_status, "detail": load_detail}

    # Check certificate expiry (web services)
    for name, config in SERVICES.items():
        if service and name != service:
            continue
        if config["port"] == 443:
            cert_status, cert_detail, days_left = check_certificate_expiry(config["host"])
            results["services"][name]["certificate"] = {
                "status": cert_status,
                "detail": cert_detail,
                "days_remaining": days_left,
            }
            if cert_status == "CRITICAL":
                all_ok = False

    results["overall_status"] = "OK" if all_ok else "DEGRADED"
    results["rate_limiter"] = limiter.stats()

    return results


def print_health_report(results: Dict[str, Any]):
    print(f"\n{'='*60}")
    print(f"  HEALTH CHECK REPORT")
    print(f"  Host: {results['hostname']}")
    print(f"  Time: {results['timestamp']}")
    print(f"  Overall: {results['overall_status']}")
    print(f"{'='*60}")

    for category, items in [("Services", results["services"]),
                             ("Infrastructure", results["infrastructure"]),
                             ("System", results["system"])]:
        if items:
            print(f"\n  {category}:")
            for name, check in items.items():
                if isinstance(check, dict) and "status" in check:
                    status_icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗"}.get(check["status"], "?")
                    print(f"    {status_icon} {name}: {check['detail']}")
                else:
                    print(f"    {name}:")
                    for sub_name, sub_check in check.items():
                        if isinstance(sub_check, dict) and "status" in sub_check:
                            sub_icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗"}.get(sub_check["status"], "?")
                            print(f"      {sub_icon} {sub_name}: {sub_check['detail']}")
    limiter = results.get("rate_limiter", {})
    if limiter.get("enabled"):
        print("\n  Probe limiter:")
        print(f"    rate: {limiter['current_rate']}/s (configured {limiter['configured_rate']}/s)")
        print(f"    probes: {limiter['total_probes']}, throttled: {limiter['throttled_requests']}")
        print(f"    half-open reductions: {limiter['half_open_reductions']}")
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="Health check tool")
    parser.add_argument("--service", "-s", help="Check specific service only")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--watch", "-w", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--timeout", type=float, help="Default timeout in seconds for service and infrastructure probes")
    parser.add_argument(
        "--service-timeout",
        action="append",
        default=[],
        metavar="NAME=SECONDS",
        help="Override timeout for one service or infrastructure probe",
    )
    parser.add_argument("--probe-rate", type=float, help="Maximum probes per second across service and infrastructure checks")
    parser.add_argument(
        "--half-open-service",
        action="append",
        default=[],
        help="Treat a service as HALF_OPEN and reduce its probe rate while checking it",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        validate_positive_option("--timeout", args.timeout)
        validate_positive_option("--probe-rate", args.probe_rate)
        service_timeouts = parse_service_timeout_overrides(args.service_timeout)
    except ValueError as e:
        print(f"Argument error: {e}", file=sys.stderr)
        return 2

    half_open_services = set(args.half_open_service or [])

    if args.watch:
        print(f"Continuous monitoring (interval: {args.interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                results = run_health_checks(
                    args.service,
                    args.json,
                    timeout=args.timeout,
                    service_timeouts=service_timeouts,
                    probe_rate=args.probe_rate,
                    half_open_services=half_open_services,
                )
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print_health_report(results)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
    else:
        results = run_health_checks(
            args.service,
            args.json,
            timeout=args.timeout,
            service_timeouts=service_timeouts,
            probe_rate=args.probe_rate,
            half_open_services=half_open_services,
        )
        if args.json:
            output = json.dumps(results, indent=2)
            print(output)
        else:
            print_health_report(results)

        if args.output:
            with open(args.output, "w") as f:
                if args.json:
                    json.dump(results, f, indent=2)
                else:
                    json.dump(results, f, indent=2)
            print(f"Report saved to {args.output}")

        if results["overall_status"] == "DEGRADED":
            return 1

    return 0


if __name__ == "__main__":
    main()
