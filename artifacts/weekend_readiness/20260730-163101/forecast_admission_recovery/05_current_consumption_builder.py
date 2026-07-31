from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.intelligence.governed_consumption import (
    decide_consumption,
    guarded_rank_score,
)

VALUATION = (
    ROOT / "data/operations/mtg_universal_market_valuation/"
    "universal_mtg_market_valuation.csv"
)
INTELLIGENCE = (
    ROOT / "data/validation/phase_10/unified_mtg_intelligence/"
    "unified_mtg_intelligence_interface.csv"
)
OUTPUT = ROOT / "data/operations/mtg_governed_consumption_integration"

FIELDS = [
    "canonical_product_id", "canonical_product_name", "product_class",
    "selected_reference_price", "selected_reference_date",
    "selected_source_type", "valuation_state", "freshness_days",
    "freshness_state", "dashboard_eligible", "model_eligible",
    "legacy_intelligence_matched", "legacy_source_product_id",
    "admission_tier", "quality_disposition", "forecast_method",
    "legacy_forecast_status", "legacy_forecast_eligible",
    "forecast_consumption_state", "governed_forecast_eligible",
    "one_year_downside_usd", "one_year_base_usd", "one_year_upside_usd",
    "three_year_downside_usd", "three_year_base_usd",
    "three_year_upside_usd", "five_year_downside_usd",
    "five_year_base_usd", "five_year_upside_usd",
    "legacy_recommendation_action", "legacy_recommendation_status",
    "legacy_recommendation_eligible", "recommendation_consumption_state",
    "governed_recommendation_eligible", "confidence",
    "suppression_reason", "guarded_rank_score", "guarded_rank",
    "currency",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--valuation", type=Path, default=VALUATION)
    parser.add_argument("--intelligence", type=Path, default=INTELLIGENCE)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    valuations = read_csv(args.valuation.resolve())
    intelligence_rows = read_csv(args.intelligence.resolve())
    if len(valuations) != 1141:
        raise SystemExit(f"Expected 1,141 valuation rows; found {len(valuations)}")

    intelligence = {
        row["universal_mtg_product_id"]: row
        for row in intelligence_rows
        if row.get("universal_mtg_product_id")
    }

    output_rows: list[dict[str, Any]] = []
    for valuation in valuations:
        product_id = valuation["canonical_product_id"]
        legacy = intelligence.get(product_id)
        decision = decide_consumption(valuation, legacy)

        score = None
        if decision.governed_forecast_eligible and legacy:
            score = guarded_rank_score(
                valuation.get("selected_reference_price"),
                legacy.get("three_year_base_usd"),
                legacy.get("confidence"),
            )

        output_rows.append({
            "canonical_product_id": product_id,
            "canonical_product_name": valuation.get(
                "canonical_product_name", ""
            ),
            "product_class": valuation.get("product_class", ""),
            "selected_reference_price": valuation.get(
                "selected_reference_price", ""
            ),
            "selected_reference_date": valuation.get(
                "selected_reference_date", ""
            ),
            "selected_source_type": valuation.get(
                "selected_source_type", ""
            ),
            "valuation_state": valuation.get("valuation_state", ""),
            "freshness_days": valuation.get("freshness_days", ""),
            "freshness_state": valuation.get("freshness_state", ""),
            "dashboard_eligible": valuation.get("dashboard_eligible", ""),
            "model_eligible": valuation.get("model_eligible", ""),
            "legacy_intelligence_matched": str(legacy is not None).lower(),
            "legacy_source_product_id": (
                legacy.get("source_product_id", "") if legacy else ""
            ),
            "admission_tier": legacy.get("admission_tier", "") if legacy else "",
            "quality_disposition": (
                legacy.get("quality_disposition", "") if legacy else ""
            ),
            "forecast_method": (
                legacy.get("forecast_method", "") if legacy else ""
            ),
            "legacy_forecast_status": (
                legacy.get("forecast_status", "") if legacy else ""
            ),
            "legacy_forecast_eligible": (
                legacy.get("forecast_eligible", "") if legacy else ""
            ),
            "forecast_consumption_state": (
                decision.forecast_consumption_state
            ),
            "governed_forecast_eligible": str(
                decision.governed_forecast_eligible
            ).lower(),
            "one_year_downside_usd": (
                legacy.get("one_year_downside_usd", "") if legacy else ""
            ),
            "one_year_base_usd": (
                legacy.get("one_year_base_usd", "") if legacy else ""
            ),
            "one_year_upside_usd": (
                legacy.get("one_year_upside_usd", "") if legacy else ""
            ),
            "three_year_downside_usd": (
                legacy.get("three_year_downside_usd", "") if legacy else ""
            ),
            "three_year_base_usd": (
                legacy.get("three_year_base_usd", "") if legacy else ""
            ),
            "three_year_upside_usd": (
                legacy.get("three_year_upside_usd", "") if legacy else ""
            ),
            "five_year_downside_usd": (
                legacy.get("five_year_downside_usd", "") if legacy else ""
            ),
            "five_year_base_usd": (
                legacy.get("five_year_base_usd", "") if legacy else ""
            ),
            "five_year_upside_usd": (
                legacy.get("five_year_upside_usd", "") if legacy else ""
            ),
            "legacy_recommendation_action": (
                legacy.get("recommendation_action", "") if legacy else ""
            ),
            "legacy_recommendation_status": (
                legacy.get("recommendation_status", "") if legacy else ""
            ),
            "legacy_recommendation_eligible": (
                legacy.get("recommendation_eligible", "") if legacy else ""
            ),
            "recommendation_consumption_state": (
                decision.recommendation_consumption_state
            ),
            "governed_recommendation_eligible": str(
                decision.governed_recommendation_eligible
            ).lower(),
            "confidence": legacy.get("confidence", "") if legacy else "",
            "suppression_reason": decision.suppression_reason,
            "guarded_rank_score": "" if score is None else score,
            "guarded_rank": "",
            "currency": "USD" if valuation.get(
                "selected_reference_price"
            ) else "",
        })

    rankable = sorted(
        [row for row in output_rows if row["guarded_rank_score"] != ""],
        key=lambda row: float(row["guarded_rank_score"]),
        reverse=True,
    )
    for rank, row in enumerate(rankable, start=1):
        row["guarded_rank"] = rank

    output_rows.sort(key=lambda row: row["canonical_product_id"])
    dashboard_rows = [
        row for row in output_rows
        if row["dashboard_eligible"] == "true"
    ]
    forecast_rows = [
        row for row in output_rows
        if row["governed_forecast_eligible"] == "true"
    ]
    recommendation_rows = [
        row for row in output_rows
        if row["governed_recommendation_eligible"] == "true"
    ]
    excluded_rows = [
        row for row in output_rows
        if row["governed_forecast_eligible"] != "true"
    ]

    output = args.output_root.resolve()
    write_csv(
        output / "universal_mtg_consumption_interface.csv",
        output_rows, FIELDS,
    )
    write_csv(
        output / "universal_mtg_dashboard_consumption.csv",
        dashboard_rows, FIELDS,
    )
    write_csv(
        output / "universal_mtg_governed_forecasts.csv",
        forecast_rows, FIELDS,
    )
    write_csv(
        output / "universal_mtg_governed_recommendations.csv",
        recommendation_rows, FIELDS,
    )
    write_csv(
        output / "universal_mtg_guarded_ranking.csv",
        rankable, FIELDS,
    )
    write_csv(
        output / "universal_mtg_consumption_exclusions.csv",
        excluded_rows, FIELDS,
    )

    checks = {
        "interface_rows_equal_1141": len(output_rows) == 1141,
        "canonical_product_ids_unique": len({
            row["canonical_product_id"] for row in output_rows
        }) == 1141,
        "asking_references_never_forecast_eligible": all(
            row["governed_forecast_eligible"] == "false"
            for row in output_rows
            if row["valuation_state"] == "CURRENT_ASKING_REFERENCE_ONLY"
        ),
        "asking_references_never_recommendation_eligible": all(
            row["governed_recommendation_eligible"] == "false"
            for row in output_rows
            if row["valuation_state"] == "CURRENT_ASKING_REFERENCE_ONLY"
        ),
        "unavailable_products_never_ranked": all(
            row["guarded_rank"] == ""
            for row in output_rows
            if row["valuation_state"] == "VALUATION_UNAVAILABLE"
        ),
        "forecast_rows_have_direct_history": all(
            row["valuation_state"] == "DIRECT_HISTORY_VALUATION"
            for row in forecast_rows
        ),
    }

    summary = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governed_products": len(output_rows),
        "legacy_intelligence_rows": len(intelligence_rows),
        "legacy_matches": sum(
            row["legacy_intelligence_matched"] == "true"
            for row in output_rows
        ),
        "dashboard_rows": len(dashboard_rows),
        "governed_forecast_rows": len(forecast_rows),
        "governed_recommendation_rows": len(recommendation_rows),
        "guarded_rank_rows": len(rankable),
        "excluded_rows": len(excluded_rows),
        "valuation_state_counts": dict(Counter(
            row["valuation_state"] for row in output_rows
        )),
        "forecast_consumption_state_counts": dict(Counter(
            row["forecast_consumption_state"] for row in output_rows
        )),
        "recommendation_consumption_state_counts": dict(Counter(
            row["recommendation_consumption_state"] for row in output_rows
        )),
        "certification_checks": checks,
    }
    (output / "universal_mtg_consumption_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
