from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_collector_v1_canonical_identity_lineage_recertification.ps1"


def test_runner_exists_and_contains_fail_closed_controls() -> None:
    assert RUNNER.is_file()
    text = RUNNER.read_text(encoding="utf-8")
    required = [
        "Set-StrictMode -Version Latest",
        '$ErrorActionPreference = "Stop"',
        "Fail-Governance",
        "STEP 1 — VERIFY DECLARED AUTHORITIES",
        "STEP 2 — RUN GOVERNANCE TESTS",
        "STEP 3 — RUN FULL RECERTIFICATION",
        "PASS_COLLECTOR_CANONICAL_IDENTITY_LINEAGE_RECERTIFICATION",
        "PASS_LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION",
        "No ranking was authorized.",
        "No purchase recommendation was authorized.",
    ]
    for token in required:
        assert token in text


def test_runner_has_no_inline_if_statement_as_hashtable_value() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "rows      = if (" not in text
    assert "rows = if (" not in text


def test_runner_parses_with_windows_powershell_when_available() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        return
    escaped = str(RUNNER).replace("'", "''")
    command = (
        "$tokens=$null; $errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',"
        "[ref]$tokens,[ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
