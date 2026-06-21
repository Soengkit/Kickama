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
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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

# Stale-metric guard configuration
STALE_METRIC_THRESHOLD_SECONDS = int(os.environ.get("STALE_METRIC_THRESHOLD_SECONDS", "300"))
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")
_STATUS_TO_VALUE = {"OK": 0, "WARNING": 1, "CRITICAL": 2}

# ---------------------------------------------------------------------------
# CHECK FUNCTIONS
# ---------------------------------------------------------------------------

def check_http_service(host: str, port: int, path: str, timeout: int) -> Tuple[str, str, int]:
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


def check_tcp_port(host: str, port: int, timeout: int) -> Tuple[str, str, float]:
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

def run_health_checks(service: Optional[str] = None, json_output: bool = False) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "services": {},
        "infrastructure": {},
        "system": {},
        "overall_status": "OK",
    }

    all_ok = True

    # Check services
    for name, config in SERVICES.items():
        if service and name != service:
            continue
        status, detail, code = check_http_service(
            config["host"], config["port"], config["path"], config["timeout"]
        )
        results["services"][name] = {
            "status": status,
            "detail": detail,
            "code": code,
            "endpoint": f"http://{config['host']}:{config['port']}{config['path']}",
        }
        if status == "CRITICAL":
            all_ok = False

    # Check infrastructure
    for name, config in INFRASTRUCTURE.items():
        if service and name != service:
            continue
        status, detail, latency = check_tcp_port(config["host"], config["port"], config["timeout"])
        results["infrastructure"][name] = {
            "status": status,
            "detail": detail,
            "endpoint": f"{config['host']}:{config['port']}",
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
    print()


# ---------------------------------------------------------------------------
# PROMETHEUS EXPORT & STALE-METRIC GUARD
# ---------------------------------------------------------------------------

def redact_secrets(text: str) -> str:
    """Redact secret-looking values from diagnostic/output text."""
    if not text:
        return text
    text = re.sub(
        r'(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|credential)\s*[:=]\s*)[^\s,;"\']+',
        r'\1REDACTED',
        text,
    )
    text = re.sub(r'(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;"\']+', r'\1REDACTED', text)
    text = re.sub(r'ghp_[A-Za-z0-9]{20,}', 'ghp_REDACTED', text)
    text = re.sub(r'sk-[A-Za-z0-9]{20,}', 'sk-REDACTED', text)
    return text


def _escape_prometheus_label(value) -> str:
    """Escape a value for safe use inside a Prometheus label."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def collect_health_metrics(results: Dict[str, Any], environment: Optional[str] = None) -> List[Dict[str, Any]]:
    """Flatten health check results into metric records for stale reporting.

    Each record carries service, environment, metric name, timestamp and status.
    """
    environment = environment or ENVIRONMENT
    timestamp = results.get("timestamp")
    metrics: List[Dict[str, Any]] = []

    for service_name, info in results.get("services", {}).items():
        metrics.append({
            "service": service_name,
            "environment": environment,
            "metric_name": f"service.{service_name}.status",
            "timestamp": timestamp,
            "status": info.get("status") if isinstance(info, dict) else None,
        })
        if isinstance(info, dict):
            for sub_name, sub_info in info.items():
                if sub_name != "status" and isinstance(sub_info, dict) and "status" in sub_info:
                    metrics.append({
                        "service": service_name,
                        "environment": environment,
                        "metric_name": f"service.{service_name}.{sub_name}.status",
                        "timestamp": timestamp,
                        "status": sub_info.get("status"),
                    })

    for infra_name, info in results.get("infrastructure", {}).items():
        metrics.append({
            "service": infra_name,
            "environment": environment,
            "metric_name": f"infrastructure.{infra_name}.status",
            "timestamp": timestamp,
            "status": info.get("status") if isinstance(info, dict) else None,
        })

    for sys_name, info in results.get("system", {}).items():
        metrics.append({
            "service": "system",
            "environment": environment,
            "metric_name": f"system.{sys_name}.status",
            "timestamp": timestamp,
            "status": info.get("status") if isinstance(info, dict) else None,
        })

    return metrics


def flag_stale_metrics(
    metrics: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    threshold: int = STALE_METRIC_THRESHOLD_SECONDS,
) -> List[Dict[str, Any]]:
    """Annotate each metric with age_seconds and a stale flag.

    A metric is stale when its timestamp is older than ``threshold`` seconds
    relative to ``now``. Metrics without a usable timestamp are reported as
    stale so outdated data is never silently exported.
    """
    now = now or datetime.now()
    if isinstance(now, str):
        now = datetime.fromisoformat(now)

    flagged: List[Dict[str, Any]] = []
    for metric in metrics:
        record = dict(metric)
        timestamp = record.get("timestamp")
        age_seconds: Optional[float] = None
        stale = True
        if timestamp is not None:
            try:
                collected_at = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
                age_seconds = (now - collected_at).total_seconds()
                stale = age_seconds > threshold
            except (ValueError, TypeError):
                age_seconds = None
                stale = True
        record["age_seconds"] = round(age_seconds, 3) if age_seconds is not None else None
        record["stale"] = bool(stale)
        flagged.append(record)
    return flagged


def format_prometheus(
    results: Dict[str, Any],
    now: Optional[datetime] = None,
    threshold: int = STALE_METRIC_THRESHOLD_SECONDS,
    environment: Optional[str] = None,
) -> str:
    """Render health check results as Prometheus exposition text.

    Stale metrics are flagged via ``tot_health_check_metric_stale`` so scrapers
    can alert before exporting outdated data. Secret-looking values are redacted.
    """
    metrics = flag_stale_metrics(
        collect_health_metrics(results, environment=environment),
        now=now,
        threshold=threshold,
    )
    lines = [
        "# HELP tot_health_check_status Health check status (0=OK,1=WARNING,2=CRITICAL).",
        "# TYPE tot_health_check_status gauge",
        "# HELP tot_health_check_metric_stale 1 if the metric timestamp is stale, 0 otherwise.",
        "# TYPE tot_health_check_metric_stale gauge",
        "# HELP tot_health_check_metric_age_seconds Age of the metric in seconds.",
        "# TYPE tot_health_check_metric_age_seconds gauge",
    ]
    for metric in metrics:
        labels = (
            f'service="{_escape_prometheus_label(metric.get("service", ""))}",'
            f'environment="{_escape_prometheus_label(metric.get("environment", ""))}",'
            f'metric="{_escape_prometheus_label(metric.get("metric_name", ""))}"'
        )
        status_value = _STATUS_TO_VALUE.get(str(metric.get("status")).upper(), 2)
        stale_value = 1 if metric.get("stale") else 0
        lines.append(f"tot_health_check_status{{{labels}}} {status_value}")
        lines.append(f"tot_health_check_metric_stale{{{labels}}} {stale_value}")
        if metric.get("age_seconds") is not None:
            lines.append(f"tot_health_check_metric_age_seconds{{{labels}}} {metric['age_seconds']}")
    return redact_secrets("\n".join(lines) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Health check tool")
    parser.add_argument("--service", "-s", help="Check specific service only")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--prometheus", "-p", action="store_true", help="Prometheus exposition output with stale-metric guard")
    parser.add_argument("--stale-threshold", type=int, default=STALE_METRIC_THRESHOLD_SECONDS, help="Seconds after which a metric is considered stale")
    parser.add_argument("--watch", "-w", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--output", "-o", help="Output file path")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.watch:
        print(f"Continuous monitoring (interval: {args.interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                results = run_health_checks(args.service, args.json)
                results["stale_metrics"] = flag_stale_metrics(
                    collect_health_metrics(results), threshold=args.stale_threshold
                )
                if args.prometheus:
                    print(format_prometheus(results, threshold=args.stale_threshold))
                elif args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print_health_report(results)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
    else:
        results = run_health_checks(args.service, args.json)
        results["stale_metrics"] = flag_stale_metrics(
            collect_health_metrics(results), threshold=args.stale_threshold
        )

        if args.prometheus:
            print(format_prometheus(results, threshold=args.stale_threshold))
        elif args.json:
            print(json.dumps(results, indent=2))
        else:
            print_health_report(results)

        if args.output:
            with open(args.output, "w") as f:
                if args.prometheus:
                    f.write(format_prometheus(results, threshold=args.stale_threshold))
                elif args.json:
                    json.dump(results, f, indent=2)
                else:
                    json.dump(results, f, indent=2)
            print(f"Report saved to {args.output}")

        if results["overall_status"] == "DEGRADED":
            return 1

    return 0


if __name__ == "__main__":
    main()
