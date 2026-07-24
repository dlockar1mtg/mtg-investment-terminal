from __future__ import annotations

import json
from pathlib import Path

from terminal2.certification.production_readiness import (
    run_production_readiness,
    write_report,
)


def test_production_readiness_passes() -> None:
    report = run_production_readiness()

    assert report.overall_status == "PASS"
    assert report.checks
    assert all(
        check.status == "PASS"
        for check in report.checks
        if check.blocking
    )

    checks_by_name = {
        check.name: check
        for check in report.checks
    }

    assert (
        checks_by_name["configuration_paths"].status
        == "PASS"
    )
    assert (
        checks_by_name["network_timeouts"].status
        == "PASS"
    )


def test_production_readiness_reports_are_written(
    tmp_path: Path,
) -> None:
    report = run_production_readiness()

    json_path, markdown_path = write_report(
        report,
        tmp_path,
    )

    assert json_path.exists()
    assert markdown_path.exists()

    payload = json.loads(
        json_path.read_text(encoding="utf-8")
    )

    assert payload["overall_status"] == "PASS"
    assert len(payload["checks"]) == len(report.checks)

    markdown = markdown_path.read_text(
        encoding="utf-8"
    )

    assert (
        "# Phase 10.4 Production-Readiness Report"
        in markdown
    )
    assert "Overall status: **PASS**" in markdown

def test_certification_runner_executes_as_script() -> None:
    import subprocess
    import sys

    repository_root = Path(__file__).resolve().parents[1]
    runner = (
        repository_root
        / "scripts"
        / "certify_phase_10_4.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(runner),
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, (
        result.stdout + "\n" + result.stderr
    )

    assert (
        "Phase 10.4 production readiness: PASS"
        in result.stdout
    )