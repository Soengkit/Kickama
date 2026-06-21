#!/usr/bin/env python3
"""Validate bounty issue bodies before they are published."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REQUIRED_SECTIONS = [
    "**Bounty:**",
    "Acceptance criteria:",
    "Commissions:",
    "Required validation:",
]

REQUIRED_COMMISSION_PARAGRAPH = (
    "You can earn an extra $5 for every bounty issue you create on your own fork "
    "of the repo, provided you keep up with submissions. We will payout the bounty "
    "you place between $5 and $25 to the submitter and you will earn an extra $5 "
    "on your payout, after you merge the best submission for your bounty. You are "
    "required to use this exact issue template & description format, including "
    "this message and the required validation. Payouts will not be given to you "
    "or other submitters without a valid build diagnostic log (not build-00000000). "
    "You are required to rename your fork to something fun and unique, and provide "
    "this exact message in your issue description."
)


@dataclass
class ValidationResult:
    path: str
    ok: bool
    errors: list[str]


def _section_after(text: str, section: str) -> str:
    marker = text.find(section)
    if marker == -1:
        return ""
    start = marker + len(section)
    next_positions = [
        text.find(other, start)
        for other in REQUIRED_SECTIONS
        if other != section and text.find(other, start) != -1
    ]
    end = min(next_positions) if next_positions else len(text)
    return text[start:end].strip()


def _first_paragraph(section_text: str) -> str:
    paragraphs = re.split(r"\n\s*\n", section_text.strip())
    return paragraphs[0].strip() if paragraphs else ""


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def validate_text(text: str, path: str = "<stdin>") -> ValidationResult:
    text = _normalize_newlines(text)
    errors: list[str] = []

    missing = [section for section in REQUIRED_SECTIONS if section not in text]
    for section in missing:
        errors.append(f"missing required section: {section}")

    section_positions = [text.find(section) for section in REQUIRED_SECTIONS]
    present_positions = [pos for pos in section_positions if pos != -1]
    if present_positions and present_positions != sorted(present_positions):
        errors.append("required sections must appear in bounty, acceptance, commissions, validation order")

    commissions = _first_paragraph(_section_after(text, "Commissions:"))
    if commissions and commissions != REQUIRED_COMMISSION_PARAGRAPH:
        errors.append("commissions paragraph does not match the required text exactly")

    validation = _section_after(text, "Required validation:")
    if validation:
        validation_lower = validation.lower()
        mentions_real_log = (
            "diagnostic/build-" in validation_lower
            and ".logd" in validation_lower
            and ("real diagnostic" in validation_lower or "generated diagnostic" in validation_lower)
        )
        excludes_stub = (
            "build-00000000" in validation_lower
            and re.search(r"(must not|not be|exclude|reject|not\s+build-00000000)", validation_lower)
        )
        if not mentions_real_log:
            errors.append("required validation must mention a real diagnostic/build-*.logd requirement")
        if not excludes_stub:
            errors.append("required validation must explicitly exclude build-00000000 diagnostics")

    return ValidationResult(path=path, ok=not errors, errors=errors)


def validate_path(path: Path) -> ValidationResult:
    try:
        return validate_text(path.read_text(encoding="utf-8"), str(path))
    except OSError as exc:
        return ValidationResult(path=str(path), ok=False, errors=[f"could not read file: {exc}"])


def validate_paths(paths: Iterable[Path]) -> list[ValidationResult]:
    return [validate_path(path) for path in paths]


def _print_text(results: list[ValidationResult]) -> None:
    for result in results:
        if result.ok:
            print(f"PASS {result.path}")
            continue
        print(f"FAIL {result.path}")
        for error in result.errors:
            print(f"  - {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate bounty issue body files for required template sections.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown issue body file(s) to validate")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable validation results")
    args = parser.parse_args(argv)

    results = validate_paths(args.paths)
    if args.json:
        print(json.dumps([result.__dict__ for result in results], indent=2))
    else:
        _print_text(results)
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
