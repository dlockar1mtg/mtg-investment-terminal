from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_8"
    / "secret_lair_historical_performance"
)

SOURCE = OUTPUT_ROOT / "secret_lair_historical_performance.csv"

UNIVERSAL = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "universal_export"
    / "latest"
    / "historical_performance.csv"
)

UIP = (
    ROOT
    / "data"
    / "operations"
    / "mtg_uip_delivery"
    / "latest"
    / "historical_performance.csv"
)

CERTIFICATION = (
    ROOT
    / "docs"
    / "phase_8"
    / "mtg_intelligence_recovery"
    / "historical_performance_forecast_separation"
    / "PHASE_8_2_1D_2_CERTIFICATION.json"
)


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    source_rows = read_csv(SOURCE)
    universal_rows = read_csv(UNIVERSAL)
    uip_rows = read_csv(UIP)

    checks = {
        "source_rows_equal_973": len(source_rows) == 973,
        "universal_rows_equal_973": len(universal_rows) == 973,
        "uip_rows_equal_973": len(uip_rows) == 973,
        "source_ids_unique": len(
            {row.get("investment_product_id") for row in source_rows}
        ) == 973,
        "delivery_ids_match": (
            {
                row.get("investment_product_id")
                for row in source_rows
            }
            == {
                row.get("investment_product_id")
                for row in universal_rows
            }
            == {
                row.get("investment_product_id")
                for row in uip_rows
            }
        ),
        "historical_returns_require_eligibility": all(
            (
                clean(row.get("historical_total_return_pct"))
                and clean(row.get("historical_cagr_pct"))
                and clean(row.get("historical_start_date"))
                and clean(row.get("historical_end_date"))
            )
            if row.get("historical_performance_eligible") == "YES"
            else (
                not clean(row.get("historical_total_return_pct"))
                and not clean(row.get("historical_cagr_pct"))
            )
            for row in source_rows
        ),
        "forecast_horizons_remain_blank": all(
            not clean(row.get("one_year_base_usd"))
            and not clean(row.get("three_year_base_usd"))
            and not clean(row.get("five_year_base_usd"))
            for row in source_rows + universal_rows + uip_rows
        ),
        "forecast_eligibility_fail_closed": all(
            row.get("forecast_eligible") == "NO"
            for row in source_rows + universal_rows + uip_rows
        ),
        "recommendations_fail_closed": all(
            row.get("recommendation_eligible") == "NO"
            for row in source_rows + universal_rows + uip_rows
        ),
        "separate_historical_contract": all(
            "historical_performance_status" in row
            and "historical_cagr_pct" in row
            for row in source_rows
        ),
    }

    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    result = {
        "status": status,
        "phase": "8.2.1D.2",
        "checks": checks,
        "counts": {
            "source_rows": len(source_rows),
            "universal_rows": len(universal_rows),
            "uip_rows": len(uip_rows),
            "historical_ready": sum(
                row.get("historical_performance_eligible") == "YES"
                for row in source_rows
            ),
            "historical_suppressed": sum(
                row.get("historical_performance_eligible") != "YES"
                for row in source_rows
            ),
        },
    }

    CERTIFICATION.parent.mkdir(parents=True, exist_ok=True)
    CERTIFICATION.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 78)
    print("PHASE 8.2.1D.2 — HISTORICAL/FORECAST SEPARATION CERTIFICATION")
    print("=" * 78)
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} | {name}")
    print(
        "PHASE 8.2.1D.2 CERTIFICATION: "
        f"{status}"
    )

    return 0 if status == "CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
