#!/usr/bin/env python3
"""
Health check tool for the Tent of Trials platform.
Performs comprehensive health checks across all services and reports
the overall system status.
"""

import argparse
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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

PROMETHEUS_STALENESS_SECONDS = 300
DISK_THRESHOLD_WARNING = 80
DISK_THRESHOLD_CRITICAL = 90
MEMORY_THRESHOLD_WARNING = 80
MEMORY_THRESHOLD_CRITICAL = 90

_SENSITIVE_PATTERNS = [
    re.compile(r'(password|secret|token|api[_-]?key|auth)[=:\s"]+([^"&\s]{3,})', re.IGNORECASE),
    re.compile(r'Bearer [A-Za-z0-9_\-\.]{10,}'),
    re.compile(r'eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'),
]

def redact_secrets(value: str) -> str:
    result = str(value)
    for pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub(lambda m: f'{m.group(1)}***REDACTED***' if m.group(1) else '***REDACTED***', result)
    return result

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
            result, detail = "OK", f"HTTP {status}"
        elif status < 500:
            result, detail = "WARNING", f"HTTP {status}: {body[:100]}"
        else:
            result, detail = "CRITICAL", f"HTTP {status}: {body[:100]}"
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

def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    elif seconds < 86400:
        return f"{seconds/3600:.1f}h"
    else:
        return f"{seconds/86400:.1f}d"

def check_prometheus_staleness(prom_url: str, threshold: int = None) -> Tuple[str, str, List[Dict[str, Any]]]:
    if threshold is None:
        threshold = PROMETHEUS_STALENESS_SECONDS
    try:
        import urllib.request
        req = urllib.request.Request(prom_url, headers={"Accept": "text/plain"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        now = time.time()
        stale_metrics: List[Dict[str, Any]] = []
        for line in content.splitlines():
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            metric_full = parts[0]
            try:
                value = float(parts[-2])
                ts = float(parts[-1])
            except ValueError:
                continue
            age = now - ts
            if age > threshold:
                metric_name = metric_full.split("{")[0] if "{" in metric_full else metric_full
                labels = ""
                if "{" in metric_full:
                    labels_str = metric_full.split("{", 1)[1].rstrip("}")
                    labels = redact_secrets(labels_str)
                stale_metrics.append({
                    "metric": metric_name,
                    "labels": labels,
                    "value": value,
                    "timestamp": ts,
                    "age_seconds": round(age, 1),
                    "age_readable": _format_age(age),
                })
        if not stale_metrics:
            return "OK", "No stale Prometheus metrics detected", []
        by_name: Dict[str, Dict[str, Any]] = {}
        for m in stale_metrics:
            key = m["metric"]
            if key not in by_name or m["age_seconds"] > by_name[key]["age_seconds"]:
                by_name[key] = m
        oldest = max(s["age_seconds"] for s in stale_metrics)
        detail = f"{len(stale_metrics)} stale metric(s) detected, oldest {threshold/60:.0f}m+ ({_format_age(oldest)})"
        if oldest > threshold * 2:
            return "CRITICAL", detail, list(by_name.values())
        else:
            return "WARNING", detail, list(by_name.values())
    except Exception as e:
        return "WARNING", f"Cannot check Prometheus staleness: {e}", []

def run_health_checks(
    service: Optional[str] = None,
    json_output: bool = False,
    prom_url: Optional[str] = None,
) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "services": {},
        "infrastructure": {},
        "system": {},
        "overall_status": "OK",
    }
    all_ok = True

    for name, config in SERVICES.items():
        if service and name != service:
            continue
        status, detail, code = check_http_service(config["host"], config["port"], config["path"], config["timeout"])
        results["services"][name] = {"status": status, "detail": detail, "code": code,
            "endpoint": f"http://{config['host']}:{config['port']}{config['path']}"}
        if status == "CRITICAL":
            all_ok = False

    for name, config in INFRASTRUCTURE.items():
        if service and name != service:
            continue
        status, detail, latency = check_tcp_port(config["host"], config["port"], config["timeout"])
        results["infrastructure"][name] = {"status": status, "detail": detail,
            "endpoint": f"{config['host']}:{config['port']}"}
        if status == "CRITICAL":
            all_ok = False

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

    for name, config in SERVICES.items():
        if service and name != service:
            continue
        if config["port"] == 443:
            cert_status, cert_detail, days_left = check_certificate_expiry(config["host"])
            results["services"][name]["certificate"] = {"status": cert_status, "detail": cert_detail, "days_remaining": days_left}
            if cert_status == "CRITICAL":
                all_ok = False

    if prom_url:
        prom_status, prom_detail, stale_list = check_prometheus_staleness(prom_url)
        results["system"]["prometheus_stale_metrics"] = {
            "status": prom_status, "detail": prom_detail,
            "staleness_threshold_seconds": PROMETHEUS_STALENESS_SECONDS,
            "stale_metrics": stale_list,
        }
        if prom_status in ("CRITICAL", "WARNING"):
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
    for category, items in [("Services", results["services"]), ("Infrastructure", results["infrastructure"]), ("System", results["system"])]:
        if items:
            print(f"\n  {category}:")
            for name, check in items.items():
                if isinstance(check, dict) and "status" in check:
                    status_icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗"}.get(check["status"], "?")
                    print(f"    {status_icon} {name}: {check['detail']}")
                    if name == "prometheus_stale_metrics" and check.get("stale_metrics"):
                        for m in check["stale_metrics"][:5]:
                            labels = f" ({m['labels']})" if m.get("labels") else ""
                            print(f"      └─ STALE: {m['metric']}{labels} age={m['age_readable']}")
                        if len(check["stale_metrics"]) > 5:
                            print(f"      └─ ... and {len(check['stale_metrics'])-5} more")
    print()

def parse_args():
    parser = argparse.ArgumentParser(description="Health check tool")
    parser.add_argument("--service", "-s", help="Check specific service only")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--watch", "-w", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--prom-url", "-p", help="Prometheus metrics URL for staleness check")
    return parser.parse_args()

def main():
    args = parse_args()
    if args.watch:
        print(f"Continuous monitoring (interval: {args.interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                results = run_health_checks(args.service, args.json, args.prom_url)
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print_health_report(results)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
    else:
        results = run_health_checks(args.service, args.json, args.prom_url)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_health_report(results)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Report saved to {args.output}")
        if results["overall_status"] == "DEGRADED":
            return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
