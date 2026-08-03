from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_model_output_validation_contract_v1.json"
MC_DIR = ROOT / "data/governance/permanence/certification/collector_v1_complete_horizon_probabilistic_forecast"
EA_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_awareness_lorwyn_forecast"
BASE_FORECAST = MC_DIR / "collector_complete_horizon_probabilistic_forecasts.csv"
BASE_COVERAGE = MC_DIR / "collector_complete_horizon_coverage_registry.csv"
LORWYN_FORECAST = EA_DIR / "collector_lorwyn_standalone_probabilistic_forecasts.csv"
TRUTH = EA_DIR / "collector_first_year_breakout_truth_registry.csv"
PREDICTIONS = EA_DIR / "collector_early_awareness_checkpoint_predictions.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_final_model_output_validation"


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def boolish(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes", "y"}


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required = [BASE_FORECAST, BASE_COVERAGE, LORWYN_FORECAST, TRUTH, PREDICTIONS]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_INPUTS:" + ";".join(missing))

    base_rows = read_csv(BASE_FORECAST)
    lorwyn_rows = read_csv(LORWYN_FORECAST)
    coverage_rows = read_csv(BASE_COVERAGE)
    truth_rows = read_csv(TRUTH)
    prediction_rows = read_csv(PREDICTIONS)
    failures: list[str] = []

    # Integrate Lorwyn and preserve one explicit user exclusion.
    integrated = [dict(row) for row in base_rows] + [dict(row) for row in lorwyn_rows]
    horizons = [int(value) for value in contract["horizons_days"]]

    # Normalize common fields across both forecast sources.
    for row in integrated:
        row.setdefault("explicit_method_id", clean(row.get("explicit_method_id")))
        row.setdefault("simulation_count", clean(row.get("simulation_count")))
        row.setdefault("current_ebay_data_used", clean(row.get("current_ebay_data_used")))
        row.setdefault("forecast_status", clean(row.get("forecast_status")) or "FORECAST_AUTHORIZED_RESEARCH")
        row.setdefault("supply_status", clean(row.get("supply_status")))
        row.setdefault("supply_overlay_status", clean(row.get("supply_overlay_status")))

    ids = {clean(row.get("canonical_product_id")) for row in integrated if clean(row.get("canonical_product_id"))}
    if len(integrated) != int(contract["required_forecast_rows"]):
        failures.append("INTEGRATED_FORECAST_ROW_COUNT_MISMATCH")
    if len(ids) != int(contract["required_forecast_products"]):
        failures.append("INTEGRATED_FORECAST_PRODUCT_COUNT_MISMATCH")

    counts_by_horizon: dict[int, int] = defaultdict(int)
    key_counts: dict[tuple[str, int], int] = defaultdict(int)
    reasonableness_rows: list[dict[str, Any]] = []

    probability_fields = [
        "probability_of_loss",
        "probability_of_50pct_gain",
        "probability_of_doubling",
    ]

    for row in integrated:
        cid = clean(row.get("canonical_product_id"))
        horizon = int(float(clean(row.get("horizon_days")) or 0))
        counts_by_horizon[horizon] += 1
        key_counts[(cid, horizon)] += 1
        current = num(row.get("current_price"))
        p10 = num(row.get("p10_price"))
        p25 = num(row.get("p25_price"))
        median_price = num(row.get("median_price"))
        p75 = num(row.get("p75_price"))
        p90 = num(row.get("p90_price"))
        method = clean(row.get("explicit_method_id"))
        simulations = int(float(clean(row.get("simulation_count")) or 0))

        row_failures: list[str] = []
        warnings: list[str] = []
        if not cid or horizon not in horizons:
            row_failures.append("INVALID_PRODUCT_OR_HORIZON")
        if not method or "GENERIC" in method.upper():
            row_failures.append("MISSING_OR_GENERIC_METHOD")
        if simulations != int(contract["simulation_count"]):
            row_failures.append("INVALID_SIMULATION_COUNT")
        if current is None or current < float(contract["reasonableness"]["minimum_allowed_price"]):
            row_failures.append("INVALID_CURRENT_PRICE")
        quantiles = [p10, p25, median_price, p75, p90]
        if any(value is None for value in quantiles):
            row_failures.append("MISSING_FORECAST_QUANTILE")
        elif not all(quantiles[index] <= quantiles[index + 1] for index in range(4)):
            row_failures.append("NON_MONOTONIC_FORECAST_QUANTILES")

        for field in probability_fields:
            value = num(row.get(field))
            if value is None or not 0.0 <= value <= 1.0:
                row_failures.append(f"INVALID_{field.upper()}")

        five_year_cagr = None
        p90_multiple = None
        if horizon == 1825 and current and median_price and p90:
            five_year_cagr = (median_price / current) ** (365.0 / 1825.0) - 1.0
            p90_multiple = p90 / current
            if five_year_cagr > float(contract["reasonableness"]["maximum_flagged_five_year_median_cagr"]):
                warnings.append("EXTREME_FIVE_YEAR_MEDIAN_CAGR_REVIEW")
            if p90_multiple > float(contract["reasonableness"]["maximum_flagged_five_year_p90_multiple"]):
                warnings.append("EXTREME_FIVE_YEAR_P90_MULTIPLE_REVIEW")

        reasonableness_rows.append({
            "canonical_product_id": cid,
            "product_name": clean(row.get("product_name")),
            "horizon_days": horizon,
            "explicit_method_id": method,
            "simulation_count": simulations,
            "current_price": current,
            "p10_price": p10,
            "median_price": median_price,
            "p90_price": p90,
            "five_year_median_cagr": None if five_year_cagr is None else round(five_year_cagr, 6),
            "five_year_p90_multiple": None if p90_multiple is None else round(p90_multiple, 6),
            "hard_failures": ";".join(row_failures),
            "review_warnings": ";".join(warnings),
            "row_valid": not row_failures,
        })
        failures.extend(f"FORECAST_ROW:{cid}:{horizon}:{failure}" for failure in row_failures)

    for horizon in horizons:
        if counts_by_horizon[horizon] != int(contract["required_forecast_products"]):
            failures.append(f"HORIZON_COUNT_MISMATCH:{horizon}:{counts_by_horizon[horizon]}")
    duplicate_keys = [key for key, count in key_counts.items() if count != 1]
    if duplicate_keys:
        failures.append("DUPLICATE_OR_MISSING_PRODUCT_HORIZON_KEYS")

    # Reclassify first-year outcomes into strong-growth and exceptional-breakout tiers.
    realized_values = [num(row.get("realized_365_return")) for row in truth_rows]
    realized_values = [value for value in realized_values if value is not None]
    exceptional_threshold = max(
        float(contract["early_awareness"]["exceptional_breakout_absolute_floor"]),
        float(np.quantile(np.asarray(realized_values, dtype=float), float(contract["early_awareness"]["exceptional_breakout_quantile"]))) if realized_values else 0.0,
    )
    strong_floor = float(contract["early_awareness"]["strong_growth_return_floor"])
    tiered_truth: list[dict[str, Any]] = []
    truth_by_id: dict[str, dict[str, Any]] = {}
    for row in truth_rows:
        realized = num(row.get("realized_365_return")) or 0.0
        strong = realized >= strong_floor
        exceptional = realized >= exceptional_threshold
        enriched = dict(row)
        enriched.update({
            "strong_growth_threshold": round(strong_floor, 6),
            "exceptional_breakout_threshold": round(exceptional_threshold, 6),
            "actual_strong_growth": strong,
            "actual_exceptional_breakout": exceptional,
            "outcome_tier": "EXCEPTIONAL_BREAKOUT" if exceptional else "STRONG_GROWTH" if strong else "NORMAL_OR_WEAK_GROWTH",
        })
        tiered_truth.append(enriched)
        truth_by_id[clean(row.get("canonical_product_id"))] = enriched

    edge_rows = [row for row in tiered_truth if "edge of eternities" in clean(row.get("product_name")).lower()]
    if not edge_rows:
        failures.append("EDGE_OF_ETERNITIES_TRUTH_ROW_MISSING")
    elif not bool(edge_rows[0]["actual_strong_growth"]):
        failures.append("EDGE_OF_ETERNITIES_NOT_CLASSIFIED_AS_STRONG_GROWTH")

    # Recompute early-awareness metrics for both outcome tiers.
    metric_rows: list[dict[str, Any]] = []
    checkpoints = [int(value) for value in contract["early_awareness"]["checkpoint_days"]]
    cutoffs = [int(value) for value in contract["early_awareness"]["selection_cutoffs"]]
    for checkpoint in checkpoints:
        rows = [row for row in prediction_rows if int(float(clean(row.get("checkpoint_day")) or 0)) == checkpoint]
        rows.sort(key=lambda row: int(float(clean(row.get("checkpoint_rank")) or 9999)))
        for label_name, truth_field in [
            ("STRONG_GROWTH", "actual_strong_growth"),
            ("EXCEPTIONAL_BREAKOUT", "actual_exceptional_breakout"),
        ]:
            total_positive = sum(bool(truth.get(truth_field)) for truth in tiered_truth)
            random_rate = total_positive / len(tiered_truth) if tiered_truth else 0.0
            for cutoff in cutoffs:
                selected = rows[: min(cutoff, len(rows))]
                tp = sum(bool(truth_by_id.get(clean(row.get("canonical_product_id")), {}).get(truth_field)) for row in selected)
                precision = tp / len(selected) if selected else 0.0
                recall = tp / total_positive if total_positive else 0.0
                metric_rows.append({
                    "checkpoint_day": checkpoint,
                    "selection_cutoff": cutoff,
                    "outcome_tier": label_name,
                    "eligible_products": len(rows),
                    "actual_positive_products": total_positive,
                    "true_positives": tp,
                    "precision": round(precision, 6),
                    "recall": round(recall, 6),
                    "random_precision_baseline": round(random_rate, 6),
                    "precision_lift_over_random": round(precision - random_rate, 6),
                    "lead_days": 365 - checkpoint,
                    "checkpoint_status": contract["early_awareness"]["day30_status"] if checkpoint == 30 else "EVALUATED",
                })

    # Preserve exactly one blocked product across six horizons.
    blocked = [row for row in coverage_rows if clean(row.get("coverage_status")) == "GOVERNED_BLOCKED_NO_FORECAST"]
    blocked_non_lorwyn = [row for row in blocked if "lorwyn eclipsed" not in clean(row.get("product_name")).lower()]
    blocked_ids = {clean(row.get("canonical_product_id")) for row in blocked_non_lorwyn if clean(row.get("canonical_product_id"))}
    if len(blocked_non_lorwyn) != 6 or len(blocked_ids) != 1:
        failures.append("FINAL_BLOCKED_COVERAGE_MUST_BE_ONE_PRODUCT_SIX_HORIZONS")
    if blocked_non_lorwyn and not all("special edition" in clean(row.get("product_name")).lower() for row in blocked_non_lorwyn):
        failures.append("LOTR_SPECIAL_EDITION_EXCLUSION_NOT_PRESERVED")

    warning_count = sum(bool(clean(row.get("review_warnings"))) for row in reasonableness_rows)
    hard_failure_count = sum(not boolish(row.get("row_valid")) for row in reasonableness_rows)
    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_FINAL_MODEL_OUTPUT_VALIDATION"

    OUTPUT.mkdir(parents=True, exist_ok=True)
    forecast_fields = sorted({key for row in integrated for key in row.keys()})
    write_csv(OUTPUT / "collector_final_integrated_49_product_forecasts.csv", integrated, forecast_fields)
    write_csv(OUTPUT / "collector_final_first_year_growth_truth_registry.csv", tiered_truth, list(tiered_truth[0].keys()) if tiered_truth else [])
    write_csv(OUTPUT / "collector_final_early_awareness_tier_metrics.csv", metric_rows, list(metric_rows[0].keys()) if metric_rows else [])
    write_csv(OUTPUT / "collector_final_forecast_reasonableness_review.csv", reasonableness_rows, list(reasonableness_rows[0].keys()) if reasonableness_rows else [])
    write_csv(OUTPUT / "collector_final_blocked_product_horizons.csv", blocked_non_lorwyn, sorted({key for row in blocked_non_lorwyn for key in row.keys()}))

    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "forecast_products": len(ids),
        "forecast_rows": len(integrated),
        "coverage_rows": len(integrated) + len(blocked_non_lorwyn),
        "forecast_counts_by_horizon": {str(h): counts_by_horizon[h] for h in horizons},
        "strong_growth_products": sum(bool(row["actual_strong_growth"]) for row in tiered_truth),
        "exceptional_breakout_products": sum(bool(row["actual_exceptional_breakout"]) for row in tiered_truth),
        "edge_of_eternities_classified_strong_growth": bool(edge_rows and edge_rows[0]["actual_strong_growth"]),
        "day30_status": contract["early_awareness"]["day30_status"],
        "reasonableness_warning_rows": warning_count,
        "reasonableness_hard_failure_rows": hard_failure_count,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_final_model_output_validation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
