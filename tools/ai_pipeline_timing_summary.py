"""Timing budget summaries for the AI pipeline.

The shell pipeline only records deterministic stage names and durations. This
module turns those records into text and JSON summaries while redacting any
metadata that looks like prompts or secrets before it can be logged.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|auth|bearer|cookie|credential|password|prompt|secret|token)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|password|prompt|secret|token)\b\s*[:=]?\s*(?:bearer\s+)?\S+"
)


@dataclass(frozen=True)
class StageTiming:
    name: str
    elapsed_seconds: float
    status: str = "ok"
    metadata: dict[str, Any] = field(default_factory=dict)


def sanitize_for_summary(value: Any) -> Any:
    """Return a JSON-safe value with prompt/secret-looking fields redacted."""

    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                cleaned[str(key)] = "[REDACTED]"
            else:
                cleaned[str(key)] = sanitize_for_summary(item)
        return cleaned

    if isinstance(value, list):
        return [sanitize_for_summary(item) for item in value]

    if isinstance(value, tuple):
        return [sanitize_for_summary(item) for item in value]

    if isinstance(value, str):
        if SECRET_KEY_RE.search(value):
            return "[REDACTED]"
        return SECRET_VALUE_RE.sub(
            lambda match: f"{match.group(1)}=[REDACTED]", value
        )

    return value


def build_timing_summary(
    stages: Iterable[StageTiming],
    *,
    budget_seconds: float | None = None,
    slowest_count: int = 3,
) -> dict[str, Any]:
    records = [
        {
            "name": stage.name,
            "elapsed_seconds": round(float(stage.elapsed_seconds), 3),
            "status": stage.status,
            "over_budget": (
                bool(budget_seconds is not None and stage.elapsed_seconds > budget_seconds)
            ),
            "metadata": sanitize_for_summary(stage.metadata),
        }
        for stage in stages
    ]
    records.sort(key=lambda item: item["name"])
    slowest = sorted(records, key=lambda item: item["elapsed_seconds"], reverse=True)[
        : max(slowest_count, 0)
    ]
    over_budget = [item for item in records if item["over_budget"]]

    return {
        "total_duration_seconds": round(
            sum(item["elapsed_seconds"] for item in records), 3
        ),
        "stage_count": len(records),
        "budget_seconds": budget_seconds,
        "over_budget_count": len(over_budget),
        "stages": records,
        "slowest_stages": slowest,
        "over_budget_stages": over_budget,
    }


def format_timing_summary(summary: dict[str, Any]) -> str:
    lines = [
        "AI Pipeline Timing Budget Summary",
        "=================================",
        f"total_duration_seconds: {summary['total_duration_seconds']:.3f}",
        f"stage_count: {summary['stage_count']}",
        f"budget_seconds: {summary['budget_seconds']}",
        f"over_budget_count: {summary['over_budget_count']}",
        "",
        "stages:",
    ]

    for stage in summary["stages"]:
        budget_label = " over_budget" if stage["over_budget"] else ""
        lines.append(
            f"  - {stage['name']}: {stage['elapsed_seconds']:.3f}s "
            f"status={stage['status']}{budget_label}"
        )

    lines.extend(["", "slowest_stages:"])
    for stage in summary["slowest_stages"]:
        lines.append(f"  - {stage['name']}: {stage['elapsed_seconds']:.3f}s")

    if summary["over_budget_stages"]:
        lines.extend(["", "over_budget_stages:"])
        for stage in summary["over_budget_stages"]:
            lines.append(f"  - {stage['name']}: {stage['elapsed_seconds']:.3f}s")

    return "\n".join(lines) + "\n"


def parse_stage(raw: str) -> StageTiming:
    parts = raw.split(":", 2)
    if len(parts) < 2:
        raise argparse.ArgumentTypeError(
            "stage must be formatted as name:elapsed_seconds[:status]"
        )
    name = parts[0].strip()
    if not name:
        raise argparse.ArgumentTypeError("stage name cannot be empty")
    try:
        elapsed = float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("elapsed_seconds must be numeric") from exc
    if elapsed < 0:
        raise argparse.ArgumentTypeError("elapsed_seconds cannot be negative")
    status = parts[2].strip() if len(parts) == 3 and parts[2].strip() else "ok"
    return StageTiming(name=name, elapsed_seconds=elapsed, status=status)


def load_stages(path: Path) -> list[StageTiming]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("timing input must be a JSON list")
    stages: list[StageTiming] = []
    for item in data:
        stages.append(
            StageTiming(
                name=str(item["name"]),
                elapsed_seconds=float(item["elapsed_seconds"]),
                status=str(item.get("status", "ok")),
                metadata=dict(item.get("metadata", {})),
            )
        )
    return stages


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize AI pipeline stage timings")
    parser.add_argument("--stage", action="append", type=parse_stage, default=[])
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-text", type=Path)
    parser.add_argument("--budget-seconds", type=float)
    parser.add_argument("--slowest-count", type=int, default=3)
    args = parser.parse_args()

    stages = list(args.stage)
    if args.input_json:
        stages.extend(load_stages(args.input_json))

    summary = build_timing_summary(
        stages,
        budget_seconds=args.budget_seconds,
        slowest_count=args.slowest_count,
    )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    text = format_timing_summary(summary)
    if args.output_text:
        args.output_text.parent.mkdir(parents=True, exist_ok=True)
        args.output_text.write_text(text, encoding="utf-8")
    else:
        print(text, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
