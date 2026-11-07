#!/usr/bin/env python3
"""Scan a repository's dependencies for known vulnerabilities.

Prints one JSON object: the ecosystem, counts by severity and one finding per
vulnerable package. Node projects are scanned with `npm audit`, Python
projects with `pip-audit`; Python severities come from the GitHub advisory
behind each finding, looked up on osv.dev.

    uv run tools/scan.py <repo-dir>
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SEVERITIES = ("critical", "high", "moderate", "low", "unknown")
OSV_URL = "https://api.osv.dev/v1/vulns/{}"
CACHE = Path.home() / ".cache" / "backlog-swarm" / "osv-severity.json"


def detect(repo: Path) -> str | None:
    if (repo / "package.json").exists():
        return "npm"
    if (repo / "requirements.txt").exists():
        return "pypi"
    return None


def empty_counts() -> dict[str, int]:
    return {s: 0 for s in SEVERITIES}


def scan_npm(repo: Path) -> dict:
    if not (repo / "package-lock.json").exists():
        return {"error": "no package-lock.json: npm audit needs a lockfile"}
    proc = subprocess.run(
        ["npm", "audit", "--json"], cwd=repo, capture_output=True, text=True, timeout=600
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": f"npm audit printed no JSON: {proc.stderr.strip()[-400:]}"}
    if "error" in report:
        return {"error": f"npm audit failed: {report['error'].get('summary', report['error'])}"}
    counts = empty_counts()
    findings = []
    for name, vuln in sorted(report.get("vulnerabilities", {}).items()):
        severity = vuln.get("severity", "unknown")
        severity = severity if severity in counts else "unknown"
        counts[severity] += 1
        fix = vuln.get("fixAvailable")
        if isinstance(fix, dict):
            fix = f"{fix.get('name')}@{fix.get('version')}" + (
                " (major)" if fix.get("isSemVerMajor") else ""
            )
        titles = [v.get("title") for v in vuln.get("via", []) if isinstance(v, dict)]
        findings.append(
            {
                "package": name,
                "range": vuln.get("range"),
                "severity": severity,
                "direct": vuln.get("isDirect", False),
                "fix": fix,
                "advisories": [t for t in titles if t],
            }
        )
    return {"counts": counts, "findings": findings}


def load_cache() -> dict[str, str]:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def osv_severity(ids: list[str], cache: dict[str, str]) -> str:
    """The GitHub advisory severity for the first id that has one."""
    ghsa = [i for i in ids if i.startswith("GHSA-")] + [i for i in ids if not i.startswith("GHSA-")]
    for vuln_id in ghsa:
        if vuln_id in cache:
            return cache[vuln_id]
        try:
            with urllib.request.urlopen(OSV_URL.format(vuln_id), timeout=20) as resp:
                record = json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        severity = (record.get("database_specific") or {}).get("severity")
        if severity:
            cache[vuln_id] = severity.lower()
            return cache[vuln_id]
    return "unknown"


def scan_pypi(repo: Path) -> dict:
    proc = subprocess.run(
        [
            "uvx", "pip-audit", "-r", "requirements.txt",
            "-f", "json", "--progress-spinner", "off",
        ],
        cwd=repo, capture_output=True, text=True, timeout=900,
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": f"pip-audit printed no JSON: {proc.stderr.strip()[-400:]}"}
    cache = load_cache()
    counts = empty_counts()
    findings = []
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            severity = osv_severity([vuln["id"], *vuln.get("aliases", [])], cache)
            severity = "moderate" if severity == "medium" else severity
            severity = severity if severity in counts else "unknown"
            counts[severity] += 1
            findings.append(
                {
                    "package": dep["name"],
                    "range": dep.get("version"),
                    "severity": severity,
                    "id": vuln["id"],
                    "fix": ", ".join(vuln.get("fix_versions", [])) or None,
                }
            )
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
    return {"counts": counts, "findings": findings}


def scan(repo: Path) -> dict:
    ecosystem = detect(repo)
    if ecosystem is None:
        return {"ecosystem": None, "error": "no package.json or requirements.txt"}
    result = scan_npm(repo) if ecosystem == "npm" else scan_pypi(repo)
    return {"ecosystem": ecosystem, **result}


def summary(result: dict) -> str:
    if "error" in result:
        return f"scan failed: {result['error']}"
    c = result["counts"]
    return f"C{c['critical']} H{c['high']} M{c['moderate']} L{c['low']}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: scan.py <repo-dir>")
    out = scan(Path(sys.argv[1]).resolve())
    print(json.dumps(out, indent=2))
    print(summary(out), file=sys.stderr)
