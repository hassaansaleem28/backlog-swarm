#!/usr/bin/env python3
"""Look through a patch for the ways an agent fakes a green build.

Errors fail a verification outright: a skipped or deleted test, a suppression
comment, a change to CI workflows or to a path the repository protects, or a
file outside the set the work was allowed to touch. Warnings are for the
verifier to judge: a loosened setting, a changed test file.

    python3 tools/diffcheck.py <patch-file> [--protect GLOB ...] [--allow GLOB ...]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ALWAYS_PROTECTED = [".github/**"]

SUPPRESSIONS = [
    (r"@ts-ignore", "TypeScript error suppressed with @ts-ignore"),
    (r"@ts-expect-error", "TypeScript error suppressed with @ts-expect-error"),
    (r"@ts-nocheck", "type checking turned off for a file"),
    (r"eslint-disable", "lint rule turned off"),
    (r"#\s*type:\s*ignore", "type error suppressed with # type: ignore"),
    (r"#\s*noqa", "lint error suppressed with # noqa"),
    (r"#\s*pragma:\s*no cover", "code excluded from coverage"),
]

SKIPS = [
    (r"\b(it|test|describe)\.skip\s*\(", "test skipped with .skip"),
    (r"\b(xit|xdescribe|xtest)\s*\(", "test skipped with x-prefix"),
    (r"\b(it|test|describe)\.only\s*\(", ".only makes every other test skip"),
    (r"\{\s*skip\s*:\s*true", "node:test case skipped"),
    (r"@pytest\.mark\.(skip|xfail)", "pytest test skipped or expected to fail"),
    (r"@unittest\.skip", "unittest test skipped"),
    (r"pytest\.skip\(", "pytest test skipped at run time"),
]

WEAKENED_SECURITY = [
    (r"allowInsecureKeySizes|allowInvalidAsymmetricKeyTypes", "JWT key checks turned off"),
    (r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED", "TLS verification turned off"),
    (r"verify\s*=\s*False", "TLS verification turned off"),
    (r"Loader\s*=\s*yaml\.(Unsafe)?Loader\b|yaml\.unsafe_load", "YAML loaded with an unsafe loader"),
    (r"algorithms\s*:\s*\[[^\]]*['\"]none['\"]", "JWT 'none' algorithm accepted"),
    (r"--legacy-peer-deps|--force\b", "dependency conflicts forced through"),
]

TEST_DEFS = re.compile(r"^\s*(def test_\w+|(it|test)\s*\(|async def test_\w+)")

LOOSENED_SETTINGS = [
    (r'"strict"\s*:\s*false', "TypeScript strict mode turned off"),
    (r'"noImplicitAny"\s*:\s*false', "noImplicitAny turned off"),
    (r"coverageThreshold|fail_under|--cov-fail-under", "coverage threshold changed"),
    (r"--passWithNoTests", "test runner told to pass with no tests"),
    (r"\|\|\s*true", "a command's failure is ignored with || true"),
]

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(_test|\.test|\.spec|^test_|/test_)[^/]*$")


@dataclass
class FileDiff:
    path: str
    deleted: bool = False
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def parse(patch: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            current = FileDiff(path=parts[1] if len(parts) == 2 else line)
            files.append(current)
        elif current is None:
            continue
        elif line.startswith("deleted file mode"):
            current.deleted = True
        elif line.startswith("+++ ") or line.startswith("--- "):
            continue
        elif line.startswith("+"):
            current.added.append(line[1:])
        elif line.startswith("-"):
            current.removed.append(line[1:])
    return files


def matches(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(path, g.rstrip("*").rstrip("/") + "/*") for g in globs)


def check(patch: str, protect: list[str], allow: list[str]) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    files = parse(patch)
    protected = ALWAYS_PROTECTED + protect
    for f in files:
        if matches(f.path, protected):
            errors.append(f"{f.path}: protected path changed")
        if allow and not matches(f.path, allow):
            errors.append(f"{f.path}: outside the files this work may touch")
        is_test = bool(TEST_PATH.search(f.path))
        if f.deleted and is_test:
            errors.append(f"{f.path}: test file deleted")
        for line in f.added:
            for pattern, why in SUPPRESSIONS + SKIPS + WEAKENED_SECURITY:
                if re.search(pattern, line):
                    errors.append(f"{f.path}: {why}: {line.strip()[:120]}")
            for pattern, why in LOOSENED_SETTINGS:
                if re.search(pattern, line):
                    warnings.append(f"{f.path}: {why}: {line.strip()[:120]}")
        removed_tests = sum(1 for l in f.removed if TEST_DEFS.match(l))
        added_tests = sum(1 for l in f.added if TEST_DEFS.match(l))
        if removed_tests > added_tests:
            errors.append(f"{f.path}: {removed_tests - added_tests} test definition(s) removed")
        elif is_test and (f.added or f.removed) and not f.deleted:
            warnings.append(f"{f.path}: test file changed; read it")
    return {
        "ok": not errors,
        "files": [f.path for f in files],
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("patch", type=Path)
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--allow", action="append", default=[])
    args = parser.parse_args()
    result = check(args.patch.read_text(errors="replace"), args.protect, args.allow)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
