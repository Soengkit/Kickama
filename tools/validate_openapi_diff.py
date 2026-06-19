#!/usr/bin/env python3
"""Runtime checks for tools/openapi_diff.lua."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUA = os.environ.get("LUA_BIN", "lua")
LUAC = os.environ.get("LUAC_BIN", "luac")
DIFF = ROOT / "tools" / "openapi_diff.lua"
SPEC = ROOT / "docs" / "openapi" / "v3.yaml"


def run(command: list[str], *, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != expect:
        output = result.stdout + result.stderr
        raise AssertionError(
            f"{' '.join(command)} exited {result.returncode}, expected {expect}\n{output}"
        )

    return result


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected output to contain {needle!r}\n{haystack}")


def main() -> None:
    run([LUAC, "-p", str(DIFF)])

    missing = run(
        [LUA, str(DIFF), "--self", "does-not-exist.yaml"],
        expect=1,
    )
    missing_output = missing.stdout + missing.stderr
    assert_contains(missing_output, "Cannot open file: does-not-exist.yaml")
    if "attempt to concatenate a nil value" in missing_output:
        raise AssertionError("missing-file path still references undefined color globals")

    self_diff = run([LUA, str(DIFF), "--self", str(SPEC)])
    assert_contains(self_diff.stdout, "No endpoint changes detected.")
    assert_contains(self_diff.stdout, "is consistent with itself.")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        left = tmpdir / "left.yaml"
        right = tmpdir / "right.yaml"
        left.write_text(
            "\n".join(
                [
                    "openapi: 3.1.0",
                    "paths:",
                    "  /old:",
                    "    get:",
                    "      operationId: getOld",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        right.write_text(
            "\n".join(
                [
                    "openapi: 3.1.0",
                    "paths:",
                    "  /new:",
                    "    get:",
                    "      operationId: getNew",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        diff = run([LUA, str(DIFF), "--left", str(left), "--right", str(right)])
        assert_contains(diff.stdout, "Added endpoints:     1")
        assert_contains(diff.stdout, "Removed endpoints:   1")
        assert_contains(diff.stdout, "+ /new")
        assert_contains(diff.stdout, "- /old")

    print("openapi_diff validation passed")


if __name__ == "__main__":
    main()
