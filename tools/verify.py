#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Install, build, test and scan a repository, and judge a patch against it.

Three modes, all printing one JSON object:

    verify.py baseline <repo-dir>
        The repository as it is: install, build, test, scan.
    verify.py check <repo-dir> --base <sha>
        A worker's self-check: the diff from <sha> to the working tree through
        the diff check, then a clean install, build, test and scan.
    verify.py full <repo-dir> --patch <file> [--severities critical,high]
        The verifier's run: baseline on the untouched checkout, apply the patch,
        diff check, clean install, build, test, scan, and a suggested verdict.

Commands come from `.swarm.yml` at the repository root when it has them, and
are otherwise worked out from package.json or requirements.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import diffcheck  # noqa: E402
import scan  # noqa: E402

VENV = ".swarm-venv"
LOCAL_ONLY = ["node_modules/", f"{VENV}/", ".pytest_cache/", "__pycache__/"]
STEP_TIMEOUT = 20 * 60


def load_config(repo: Path) -> dict:
    declared = {}
    swarm_file = repo / ".swarm.yml"
    if swarm_file.exists():
        declared = yaml.safe_load(swarm_file.read_text()) or {}
    ecosystem = scan.detect(repo)
    detected: dict = {"install": None, "build": None, "test": None}
    if ecosystem == "npm":
        package = json.loads((repo / "package.json").read_text())
        scripts = package.get("scripts", {})
        lock = (repo / "package-lock.json").exists()
        detected["install"] = "npm ci" if lock else "npm install"
        if "build" in scripts:
            detected["build"] = "npm run build"
        test_script = scripts.get("test", "")
        if test_script and "no test specified" not in test_script:
            detected["test"] = "npm test"
    elif ecosystem == "pypi":
        reqs = ["-r requirements.txt"]
        for extra in ("requirements-dev.txt", "requirements-test.txt"):
            if (repo / extra).exists():
                reqs.append(f"-r {extra}")
        detected["install"] = (
            f"uv venv {VENV} --quiet --allow-existing && "
            f"uv pip install --quiet --python {VENV}/bin/python {' '.join(reqs)} pytest"
        )
        if any((repo / d).exists() for d in ("tests", "test")) or list(repo.glob("test_*.py")):
            detected["test"] = f"{VENV}/bin/python -m pytest -q -p no:cacheprovider"
    return {
        "ecosystem": ecosystem,
        "install": declared.get("install", detected["install"]),
        "build": declared.get("build", detected["build"]),
        "test": declared.get("test", detected["test"]),
        "protected": list(declared.get("protected") or []),
        "from_swarm_yml": sorted(k for k in ("install", "build", "test") if k in declared),
    }


def keep_local(repo: Path) -> None:
    """Keep install output out of `git add -A` without touching .gitignore."""
    exclude = repo / ".git" / "info" / "exclude"
    if not exclude.parent.exists():
        return
    present = exclude.read_text() if exclude.exists() else ""
    missing = [p for p in LOCAL_ONLY if p not in present.splitlines()]
    if missing:
        exclude.write_text(present.rstrip("\n") + "\n" + "\n".join(missing) + "\n")


def clean(repo: Path) -> None:
    for name in ("node_modules", VENV):
        shutil.rmtree(repo / name, ignore_errors=True)


def run(command: str | None, repo: Path) -> dict:
    if not command:
        return {"ran": False}
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command, shell=True, cwd=repo, capture_output=True, text=True, timeout=STEP_TIMEOUT
        )
        output, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        code = None
    return {
        "ran": True,
        "command": command,
        "ok": code == 0,
        "exit": code,
        "seconds": round(time.monotonic() - started, 1),
        "tail": "\n".join(output.strip().splitlines()[-20:]),
        "_output": output,
    }


COUNT_PATTERNS = {
    "passed": [r"(\d+) passed", r"(?:#|ℹ) pass (\d+)", r"(\d+) passing"],
    "failed": [r"(\d+) failed", r"(?:#|ℹ) fail (\d+)", r"(\d+) failing"],
    "errors": [r"(\d+) errors?\b"],
    "skipped": [r"(\d+) skipped", r"(?:#|ℹ) skipped (\d+)", r"(\d+) pending", r"(?:#|ℹ) todo (\d+)"],
}


def test_counts(output: str) -> dict:
    counts = {}
    for key, patterns in COUNT_PATTERNS.items():
        found = 0
        for pattern in patterns:
            hits = re.findall(pattern, output, flags=re.MULTILINE)
            if hits:
                found = int(hits[-1])
                break
        counts[key] = found
    return counts


def build_test_scan(repo: Path, config: dict) -> dict:
    keep_local(repo)
    steps = {"install": run(config["install"], repo)}
    if steps["install"].get("ok", True):
        steps["build"] = run(config["build"], repo)
        steps["test"] = run(config["test"], repo)
        if steps["test"]["ran"]:
            steps["test"].update(test_counts(steps["test"]["_output"]))
    steps["scan"] = scan.scan(repo)
    for step in steps.values():
        step.pop("_output", None)
    return steps


def at_or_above(counts: dict, severities: list[str]) -> int:
    return sum(counts.get(s, 0) for s in severities)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def mode_baseline(repo: Path) -> dict:
    config = load_config(repo)
    return {"mode": "baseline", "config": config, "steps": build_test_scan(repo, config)}


def mode_check(repo: Path, base: str) -> dict:
    config = load_config(repo)
    keep_local(repo)
    git(repo, "add", "-A")
    diff = git(repo, "diff", "--cached", "--binary", base).stdout
    git(repo, "reset", "-q")
    checked = diffcheck.check(diff, config["protected"], [])
    clean(repo)
    return {
        "mode": "check",
        "config": config,
        "diffcheck": checked,
        "steps": build_test_scan(repo, config),
    }


def mode_full(repo: Path, patch: Path, severities: list[str]) -> dict:
    config = load_config(repo)
    result: dict = {"mode": "full", "patch_sha256": sha256(patch), "config": config}
    result["before"] = build_test_scan(repo, config)
    clean(repo)
    git(repo, "checkout", "-q", "--", ".")
    git(repo, "clean", "-fdq")
    applied = git(repo, "apply", "--index", "--whitespace=nowarn", str(patch.resolve()))
    result["applies"] = applied.returncode == 0
    if not result["applies"]:
        result["apply_error"] = applied.stderr.strip()[-1000:]
        result["verdict"] = "FAIL"
        result["reasons"] = ["patch does not apply to the base"]
        return result
    config = load_config(repo)
    result["diffcheck"] = diffcheck.check(patch.read_text(errors="replace"), config["protected"], [])
    result["after"] = build_test_scan(repo, config)
    result["verdict"], result["reasons"] = judge(result, severities)
    return result


def judge(result: dict, severities: list[str]) -> tuple[str, list[str]]:
    before, after = result["before"], result["after"]
    reasons = []
    if not after["install"].get("ok", True):
        reasons.append("install fails after the patch")
    if after.get("build", {}).get("ran") and not after["build"]["ok"]:
        reasons.append("build fails after the patch")
    test = after.get("test", {})
    if test.get("ran"):
        if not test["ok"] or test.get("failed") or test.get("errors"):
            reasons.append(
                f"tests fail after the patch ({test.get('failed', 0)} failed, "
                f"{test.get('errors', 0)} errors)"
            )
        if test.get("passed", 0) < before.get("test", {}).get("passed", 0):
            reasons.append(
                f"fewer tests pass than before ({before['test']['passed']} → {test['passed']})"
            )
    scan_after = after["scan"]
    if "error" in scan_after:
        reasons.append(f"scan failed after the patch: {scan_after['error']}")
    else:
        left = at_or_above(scan_after["counts"], severities)
        if left:
            reasons.append(f"{left} vulnerabilities at {','.join(severities)} remain")
    if not result["diffcheck"]["ok"]:
        reasons.extend(result["diffcheck"]["errors"])
    return ("PASS" if not reasons else "FAIL"), reasons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    p_base = sub.add_parser("baseline")
    p_base.add_argument("repo", type=Path)
    p_check = sub.add_parser("check")
    p_check.add_argument("repo", type=Path)
    p_check.add_argument("--base", required=True)
    p_full = sub.add_parser("full")
    p_full.add_argument("repo", type=Path)
    p_full.add_argument("--patch", type=Path, required=True)
    p_full.add_argument("--severities", default="critical,high")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.mode == "baseline":
        out = mode_baseline(repo)
    elif args.mode == "check":
        out = mode_check(repo, args.base)
    else:
        out = mode_full(repo, args.patch, [s.strip() for s in args.severities.split(",")])
    print(json.dumps(out, indent=2))
    if out.get("verdict"):
        print(f"verdict: {out['verdict']} {'; '.join(out['reasons'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
