from __future__ import annotations

import ast
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_collector_v1_canonical_identity_lineage_recertification.py"


def test_python_runner_exists_and_compiles() -> None:
    assert RUNNER.is_file()
    py_compile.compile(str(RUNNER), doraise=True)


def test_python_runner_contains_fail_closed_controls() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    required = [
        "COLLECTOR GOVERNANCE EXECUTION BLOCKED",
        "No calibration was authorized.",
        "No ranking was authorized.",
        "No purchase recommendation was authorized.",
        "PASS_COLLECTOR_CANONICAL_IDENTITY_LINEAGE_RECERTIFICATION",
        "PASS_LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION",
        "test_collector_v1*.py",
        "git",
        "status",
        "--porcelain",
    ]
    for token in required:
        assert token in text


def test_python_runner_has_no_shell_or_powershell_dependency() -> None:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    lowered = "\n".join(string_literals).lower()
    assert "powershell" not in lowered
    assert ".ps1" not in lowered
    assert "cmd.exe" not in lowered
    assert "shell=true" not in RUNNER.read_text(encoding="utf-8").lower()


def test_python_runner_requires_exact_final_counts() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    for token in [
        'len(final_rows) == 294',
        'len(unique_keys) == 294',
        'len(unique_products) == 49',
        'len(blocked_rows) == 6',
        'len(lineage_rows) == 294',
        'summary.get("coverage_rows") == 300',
    ]:
        assert token in text
