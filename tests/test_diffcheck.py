import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import diffcheck  # noqa: E402


def patch(path: str, added: list[str] = (), removed: list[str] = (), deleted: bool = False) -> str:
    lines = [f"diff --git a/{path} b/{path}"]
    if deleted:
        lines.append("deleted file mode 100644")
    lines += [f"--- a/{path}", f"+++ b/{path}", "@@ -1 +1 @@"]
    lines += [f"-{line}" for line in removed] + [f"+{line}" for line in added]
    return "\n".join(lines) + "\n"


def test_a_plain_upgrade_is_clean():
    result = diffcheck.check(patch("package.json", ['"lodash": "4.18.1"'], ['"lodash": "4.17.15"']), [], [])
    assert result["ok"]
    assert result["files"] == ["package.json"]


def test_turning_a_security_check_off_fails():
    result = diffcheck.check(patch("src/app.js", ["jwt.sign(p, k, { allowInsecureKeySizes: true })"]), [], [])
    assert not result["ok"]
    assert "JWT key checks turned off" in result["errors"][0]


def test_skipping_a_test_fails():
    result = diffcheck.check(patch("test/a.test.js", ["test.skip('totals', () => {})"]), [], [])
    assert not result["ok"]


def test_removing_a_test_fails():
    result = diffcheck.check(patch("tests/test_billing.py", removed=["def test_totals(client):"]), [], [])
    assert any("test definition" in e for e in result["errors"])


def test_deleting_a_test_file_fails():
    result = diffcheck.check(patch("tests/test_billing.py", deleted=True), [], [])
    assert any("test file deleted" in e for e in result["errors"])


def test_ci_workflows_are_always_protected():
    result = diffcheck.check(patch(".github/workflows/publish.yml", ["on: push"]), [], [])
    assert any("protected path" in e for e in result["errors"])


def test_paths_a_repository_protects():
    result = diffcheck.check(patch("migrations/0002.sql", ["DROP TABLE invoices;"]), ["migrations/**"], [])
    assert not result["ok"]


def test_files_outside_the_packet_fail():
    result = diffcheck.check(patch("src/other.js", ["x"]), [], ["src/routes/**"])
    assert any("outside the files" in e for e in result["errors"])


def test_a_loosened_setting_is_a_warning():
    result = diffcheck.check(patch("tsconfig.json", ['"strict": false']), [], [])
    assert result["ok"]
    assert result["warnings"]
