from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

RECOVERY_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_8"
    / "secret_lair_history_recovery"
)

CANDIDATE = (
    RECOVERY_ROOT
    / "candidate_master_secret_lair_price_history.csv"
)

D2_SCRIPT = (
    ROOT
    / "scripts"
    / "build_phase_8_2_1d_2_secret_lair_historical_performance.py"
)

EVALUATION = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "ebay_matching"
    / "production_refresh"
    / "full_model_evaluation"
    / "secret_lair_full_model_evaluation.csv"
)

VALIDATION_OUTPUT = RECOVERY_ROOT / "historical_performance_validation"


def clean(value: Any) -> str:
    return str(value or "").strip()


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "phase_8_2_1d_2_builder",
        D2_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load D.2 builder.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=CANDIDATE)
    parser.add_argument(
        "--evaluation",
        type=Path,
        default=EVALUATION,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=VALIDATION_OUTPUT,
    )
    args = parser.parse_args()

    if not args.candidate.is_file():
        raise FileNotFoundError(args.candidate)

    builder = load_builder()

    # Redirect all delivery outputs into isolated validation locations.
    builder.UNIVERSAL_LATEST = args.output_root / "universal"
    builder.UIP_LATEST = args.output_root / "uip"

    result = builder.build(
        args.candidate,
        args.evaluation,
        args.output_root / "source",
    )

    rows = read_csv(
        args.output_root
        / "source"
        / "secret_lair_historical_performance.csv"
    )

    ready = [
        row for row in rows
        if row["historical_performance_eligible"] == "YES"
    ]
    suppressed = [
        row for row in rows
        if row["historical_performance_eligible"] != "YES"
    ]

    checks = {
        "d2_validation_certified": result["status"] == "CERTIFIED",
        "rows_equal_973": len(rows) == 973,
        "historical_ready_products_found": len(ready) > 0,
        "ready_rows_have_returns": all(
            clean(row["historical_total_return_pct"])
            and clean(row["historical_cagr_pct"])
            for row in ready
        ),
        "suppressed_rows_have_no_returns": all(
            not clean(row["historical_total_return_pct"])
            and not clean(row["historical_cagr_pct"])
            for row in suppressed
        ),
        "forecast_boundary_preserved": all(
            row["forecast_eligible"] == "NO"
            and row["recommendation_eligible"] == "NO"
            and not clean(row["one_year_base_usd"])
            and not clean(row["three_year_base_usd"])
            and not clean(row["five_year_base_usd"])
            for row in rows
        ),
    }

    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    output = {
        "status": status,
        "phase": "8.2.1D.3-validation",
        "historical_ready_products": len(ready),
        "historical_suppressed_products": len(suppressed),
        "checks": checks,
        "isolated_outputs": result["outputs"],
    }

    path = (
        RECOVERY_ROOT
        / "PHASE_8_2_1D_3_NO_LOSS_VALIDATION.json"
    )
    path.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 78)
    print("PHASE 8.2.1D.3 — NO-LOSS HISTORICAL VALIDATION")
    print("=" * 78)
    print(f"Historical-ready products: {len(ready)}")
    print(f"Suppressed products: {len(suppressed)}")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} | {name}")
    print(f"PHASE 8.2.1D.3 NO-LOSS VALIDATION: {status}")
    return 0 if status == "CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
