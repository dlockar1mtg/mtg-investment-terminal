from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_product_specific_forecast_differentiation_contract_v1.json"
PRODUCTION = ROOT / "data/governance/permanence/certification/collector_v1_production_forecast_overlay_ranking/collector_production_forecasts.csv"
HISTORY = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
COMPARABLE = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_comparable_pool_certification.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_product_specific_forecast_differentiation_audit"


def clean(value: Any) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def num(value: Any) -> float | None:
    try:
        return float(clean(value).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def first(headers: set[str], candidates: list[str]) -> str:
    return next((name for name in candidates if name in headers), "")


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required = [PRODUCTION, HISTORY, COMPARABLE]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_INPUTS:" + ";".join(missing))

    forecasts = read_csv(PRODUCTION)
    history = read_csv(HISTORY)
    comparables = read_csv(COMPARABLE)
    failures: list[str] = []

    grouped: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    for row in forecasts:
        horizon = int(num(row.get("horizon_days")) or 0)
        grouped[(horizon, clean(row.get("route")))].append(row)

    dispersion_rows: list[dict[str, Any]] = []
    duplicate_rows: list[dict[str, Any]] = []
    for (horizon, route), rows in sorted(grouped.items()):
        values = [round(num(row.get("base_expected_return")) or 0.0, 6) for row in rows]
        counts = Counter(values)
        unique_ratio = len(counts) / len(values) if values else 0.0
        max_share = max(counts.values()) / len(values) if values else 1.0
        gate = route == "DIRECT_HISTORY_LIMITED" or (
            unique_ratio >= contract["minimum_within_route_unique_return_ratio"]
            and max_share <= contract["maximum_single_return_share"]
        )
        dispersion_rows.append({
            "horizon_days": horizon,
            "route": route,
            "forecast_rows": len(rows),
            "unique_returns": len(counts),
            "unique_return_ratio": round(unique_ratio, 6),
            "largest_identical_return_share": round(max_share, 6),
            "minimum_return": min(values) if values else "",
            "median_return": median(values) if values else "",
            "maximum_return": max(values) if values else "",
            "differentiation_gate_passed": gate,
        })
        for value, count in counts.items():
            if count > 1:
                matching = [row for row in rows if round(num(row.get("base_expected_return")) or 0.0, 6) == value]
                duplicate_rows.append({
                    "horizon_days": horizon,
                    "route": route,
                    "shared_return": value,
                    "product_count": count,
                    "product_ids": "|".join(clean(row.get("canonical_product_id")) for row in matching),
                    "product_names": "|".join(clean(row.get("product_name")) for row in matching),
                    "provenance_explanation_present": False,
                })

    history_headers = set(history[0]) if history else set()
    comparable_headers = set(comparables[0]) if comparables else set()
    schema_rows = [{
        "dataset": "historical_observation_ledger",
        "row_count": len(history),
        "identity_field": first(history_headers, ["canonical_product_id", "product_id", "target_canonical_product_id", "tcgplayer_product_id"]),
        "date_field": first(history_headers, ["observation_date", "observed_at_utc", "date", "snapshot_date", "as_of_date"]),
        "price_field": first(history_headers, ["price", "market_price", "selected_price", "current_price", "observed_price"]),
        "target_field": "",
        "comparable_member_field": "",
        "weight_field": "",
        "columns": "|".join(sorted(history_headers)),
    }, {
        "dataset": "comparable_pool_certification",
        "row_count": len(comparables),
        "identity_field": "",
        "date_field": "",
        "price_field": "",
        "target_field": first(comparable_headers, ["target_canonical_product_id", "canonical_product_id", "target_product_id"]),
        "comparable_member_field": first(comparable_headers, ["comparable_canonical_product_id", "comparable_product_id", "candidate_canonical_product_id", "peer_product_id"]),
        "weight_field": first(comparable_headers, ["similarity_score", "comparable_weight", "match_score", "confidence_score"]),
        "columns": "|".join(sorted(comparable_headers)),
    }]

    if any(not row["differentiation_gate_passed"] for row in dispersion_rows):
        failures.append("CURRENT_PRODUCTION_FORECASTS_NOT_PRODUCT_SPECIFIC")
    if any(not row["provenance_explanation_present"] for row in duplicate_rows):
        failures.append("IDENTICAL_RETURNS_LACK_PRODUCT_LEVEL_PROVENANCE")
    if not all(schema_rows[0][field] for field in ["identity_field", "date_field", "price_field"]):
        failures.append("HISTORY_SCHEMA_INCOMPLETE_FOR_PRODUCT_SPECIFIC_REFIT")
    if not all(schema_rows[1][field] for field in ["target_field", "comparable_member_field"]):
        failures.append("COMPARABLE_SCHEMA_INCOMPLETE_FOR_TARGET_SPECIFIC_FORECAST")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_current_forecast_return_dispersion.csv", dispersion_rows, [
        "horizon_days", "route", "forecast_rows", "unique_returns", "unique_return_ratio",
        "largest_identical_return_share", "minimum_return", "median_return", "maximum_return",
        "differentiation_gate_passed",
    ])
    write_csv(OUTPUT / "collector_identical_return_groups.csv", duplicate_rows, [
        "horizon_days", "route", "shared_return", "product_count", "product_ids", "product_names",
        "provenance_explanation_present",
    ])
    write_csv(OUTPUT / "collector_product_specific_source_schema_inventory.csv", schema_rows, [
        "dataset", "row_count", "identity_field", "date_field", "price_field", "target_field",
        "comparable_member_field", "weight_field", "columns",
    ])

    summary = {
        "block_name": "Collector Product-Specific Forecast Differentiation Audit",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "production_forecast_rows": len(forecasts),
        "dispersion_groups": len(dispersion_rows),
        "dispersion_groups_passed": sum(bool(row["differentiation_gate_passed"]) for row in dispersion_rows),
        "identical_return_groups": len(duplicate_rows),
        "history_rows": len(history),
        "comparable_rows": len(comparables),
        "product_specific_refit_authorized": not any(failure.endswith("INCOMPLETE_FOR_PRODUCT_SPECIFIC_REFIT") or failure.endswith("INCOMPLETE_FOR_TARGET_SPECIFIC_FORECAST") for failure in failures),
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_PRODUCT_SPECIFIC_FORECAST_DIFFERENTIATION_AUDIT" if not failures else "FAIL_COLLECTOR_PRODUCT_SPECIFIC_FORECAST_DIFFERENTIATION_AUDIT",
    }
    (OUTPUT / "collector_product_specific_forecast_differentiation_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
