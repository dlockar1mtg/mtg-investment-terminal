from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from terminal2.certification.production_readiness import (
    run_production_readiness,
    write_report,
)


def main() -> int:
    report = run_production_readiness()

    output_directory = (
        REPOSITORY_ROOT
        / "data"
        / "validation"
        / "phase_10"
        / "production_readiness"
    )

    json_path, markdown_path = write_report(
        report,
        output_directory,
    )

    print(
        "Phase 10.4 production readiness: "
        f"{report.overall_status}"
    )

    for check in report.checks:
        print(
            f"{check.status:<4} "
            f"{check.name}: "
            f"{check.details}"
        )

    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")

    return 0 if report.overall_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())