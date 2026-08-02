from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_probabilistic_calibration_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_final_probabilistic_calibration"


def clean(value: Any) -> str:
    return str(value or "").strip()


def norm(value: Any) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in clean(value)).split())


def num(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(clean(value)[:10])
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nearest_forward_returns(observations: list[tuple[date, float]], horizon: int, tolerance: int) -> list[float]:
    results: list[float] = []
    ordered = sorted(observations)
    for index, (start_date, start_price) in enumerate(ordered):
        target_days = horizon
        candidates: list[tuple[int, float]] = []
        for end_date, end_price in ordered[index + 1 :]:
            distance = (end_date - start_date).days
            if distance < horizon - tolerance:
                continue
            if distance > horizon + tolerance:
                break
            candidates.append((abs(distance - target_days), end_price))
        if candidates and start_price > 0:
            _, end_price = min(candidates, key=lambda item: item[0])
            results.append(end_price / start_price - 1.0)
    return results


def brier(probability: float, outcomes: list[bool]) -> float | None:
    if not outcomes:
        return None
    return mean((probability - (1.0 if outcome else 0.0)) ** 2 for outcome in outcomes)


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    paths = {name: ROOT / relative for name, relative in contract["authorities"].items()}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_AUTHORITY:" + ";".join(missing))

    forecasts = read_csv(paths["final_forecasts"])
    lineage = read_csv(paths["forecast_lineage"])
    history = read_csv(paths["historical_observations"])
    authority = read_csv(paths["current_price_authority"])
    canonical_summary = json.loads(paths["canonical_summary"].read_text(encoding="utf-8"))
    failures: list[str] = []

    authority_by_id = {clean(row["canonical_product_id"]): row for row in authority}
    history_by_id: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in history:
        cid = clean(row.get("canonical_product_id"))
        observation_date = parse_date(row.get("observation_date"))
        price = num(row.get("market_price"))
        if cid and observation_date and price and price > 0:
            history_by_id[cid].append((observation_date, price))

    lineage_keys = Counter((clean(row.get("canonical_product_id")), int(float(clean(row.get("horizon_days")) or 0))) for row in lineage)
    open_lineage = [row for row in lineage if clean(row.get("lineage_closed")).lower() not in {"true", "1", "yes"}]
    if canonical_summary.get("status") != "PASS_COLLECTOR_CANONICAL_IDENTITY_LINEAGE_RECERTIFICATION":
        failures.append("CANONICAL_RECERTIFICATION_NOT_PASS")

    row_audit: list[dict[str, Any]] = []
    coherence_rows: list[dict[str, Any]] = []
    extreme_rows: list[dict[str, Any]] = []
    historical_outcomes: dict[tuple[str, int], list[float]] = {}
    keys = Counter()

    threshold_map = {
        90: contract["reasonableness_thresholds"]["maximum_90_day_median_return"],
        180: contract["reasonableness_thresholds"]["maximum_180_day_median_return"],
        365: contract["reasonableness_thresholds"]["maximum_365_day_median_return"],
        730: contract["reasonableness_thresholds"]["maximum_730_day_median_return"],
        1095: contract["reasonableness_thresholds"]["maximum_1095_day_median_return"],
        1825: contract["reasonableness_thresholds"]["maximum_1825_day_median_return"],
    }

    for row in forecasts:
        cid = clean(row.get("canonical_product_id"))
        horizon = int(float(clean(row.get("horizon_days")) or 0))
        keys[(cid, horizon)] += 1
        authority_row = authority_by_id.get(cid)
        current_price = num(row.get("current_price"))
        authority_price = num(authority_row.get("current_price")) if authority_row else None
        quantiles = [num(row.get(field)) for field in ["p10_price", "p25_price", "median_price", "p75_price", "p90_price"]]
        probabilities = [num(row.get(field)) for field in ["probability_of_loss", "probability_of_50pct_gain", "probability_of_doubling"]]
        structural_flags: list[str] = []
        reasonableness_flags: list[str] = []

        if authority_row is None:
            structural_flags.append("UNKNOWN_IDENTITY")
        elif norm(row.get("product_name")) != norm(authority_row.get("product_name")):
            structural_flags.append("NAME_ID_MISMATCH")
        if current_price is None or current_price <= 0:
            structural_flags.append("INVALID_CURRENT_PRICE")
        if authority_price is None or current_price is None or abs(current_price - authority_price) > 0.01:
            structural_flags.append("CURRENT_PRICE_AUTHORITY_MISMATCH")
        if any(value is None or value <= 0 for value in quantiles):
            structural_flags.append("INVALID_QUANTILE_PRICE")
        elif quantiles != sorted(quantiles):
            structural_flags.append("QUANTILE_ORDER_INVALID")
        if any(value is None or value < 0 or value > 1 for value in probabilities):
            structural_flags.append("INVALID_PROBABILITY")
        if lineage_keys[(cid, horizon)] != 1:
            structural_flags.append("LINEAGE_KEY_NOT_UNIQUE")

        median_price = quantiles[2] if len(quantiles) == 5 else None
        median_return = median_price / current_price - 1.0 if median_price and current_price else None
        interval_width_return = (quantiles[4] - quantiles[0]) / current_price if all(value is not None for value in quantiles) and current_price else None
        if median_return is not None and median_return > float(threshold_map.get(horizon, 20.0)):
            reasonableness_flags.append("EXTREME_MEDIAN_RETURN")
        if interval_width_return is not None and interval_width_return > float(contract["reasonableness_thresholds"]["extreme_interval_width_return"]):
            reasonableness_flags.append("EXTREME_INTERVAL_WIDTH")

        outcomes = nearest_forward_returns(
            history_by_id.get(cid, []),
            horizon,
            int(contract["historical_validation"]["forward_window_tolerance_days"]),
        )
        historical_outcomes[(cid, horizon)] = outcomes
        min_calibrated = int(contract["historical_validation"]["minimum_windows_calibrated"])
        min_limited = int(contract["historical_validation"]["minimum_windows_limited"])
        if structural_flags:
            status = "BLOCKED"
        elif reasonableness_flags:
            status = "REASONABLENESS_REVIEW_REQUIRED"
        elif len(outcomes) >= min_calibrated:
            status = "CALIBRATED"
        elif len(outcomes) >= min_limited:
            status = "CALIBRATED_WITH_LIMITATIONS"
        else:
            status = "INSUFFICIENT_REALIZED_VALIDATION"

        audit = {
            "canonical_product_id": cid,
            "product_name": clean(row.get("product_name")),
            "horizon_days": horizon,
            "explicit_method_id": clean(row.get("explicit_method_id")),
            "current_price": current_price,
            "median_price": median_price,
            "median_expected_return_recomputed": round(median_return, 6) if median_return is not None else "",
            "interval_width_return": round(interval_width_return, 6) if interval_width_return is not None else "",
            "realized_forward_windows": len(outcomes),
            "structural_flags": "|".join(structural_flags),
            "reasonableness_flags": "|".join(reasonableness_flags),
            "calibration_status": status,
            "forecast_values_modified": False,
        }
        row_audit.append(audit)
        if reasonableness_flags:
            extreme_rows.append(audit)

    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in row_audit:
        by_product[row["canonical_product_id"]].append(row)
    for cid, rows in by_product.items():
        ordered = sorted(rows, key=lambda row: int(row["horizon_days"]))
        for previous, current in zip(ordered, ordered[1:]):
            previous_return = num(previous.get("median_expected_return_recomputed"))
            current_return = num(current.get("median_expected_return_recomputed"))
            previous_width = num(previous.get("interval_width_return"))
            current_width = num(current.get("interval_width_return"))
            flags: list[str] = []
            if previous_return is not None and current_return is not None and abs(current_return - previous_return) > float(contract["reasonableness_thresholds"]["maximum_median_return_jump_between_adjacent_horizons"]):
                flags.append("ADJACENT_MEDIAN_RETURN_JUMP")
            if previous_width and current_width is not None and current_width / previous_width < float(contract["reasonableness_thresholds"]["minimum_interval_width_growth_ratio"]):
                flags.append("LONGER_HORIZON_INTERVAL_CONTRACTION")
            coherence_rows.append({
                "canonical_product_id": cid,
                "product_name": current["product_name"],
                "previous_horizon_days": previous["horizon_days"],
                "current_horizon_days": current["horizon_days"],
                "previous_median_return": previous_return,
                "current_median_return": current_return,
                "previous_interval_width_return": previous_width,
                "current_interval_width_return": current_width,
                "coherence_flags": "|".join(flags),
                "review_required": bool(flags),
            })
            if flags:
                extreme_rows.append({**current, "reasonableness_flags": "|".join(flags)})

    group_rows: list[dict[str, Any]] = []
    method_groups: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    for row in forecasts:
        method_groups[(int(float(row["horizon_days"])), clean(row.get("explicit_method_id")))].append(row)
    for (horizon, method), rows in sorted(method_groups.items()):
        realized: list[float] = []
        brier_loss_values: list[float] = []
        brier_50_values: list[float] = []
        brier_double_values: list[float] = []
        coverage_10_90: list[bool] = []
        for row in rows:
            cid = clean(row["canonical_product_id"])
            outcomes = historical_outcomes.get((cid, horizon), [])
            current_price = num(row.get("current_price"))
            p10 = num(row.get("p10_price"))
            p90 = num(row.get("p90_price"))
            if not current_price:
                continue
            low_return = p10 / current_price - 1.0 if p10 else None
            high_return = p90 / current_price - 1.0 if p90 else None
            realized.extend(outcomes)
            if low_return is not None and high_return is not None:
                coverage_10_90.extend(low_return <= outcome <= high_return for outcome in outcomes)
            for probability_field, event, target in [
                ("probability_of_loss", lambda value: value < 0, brier_loss_values),
                ("probability_of_50pct_gain", lambda value: value >= 0.5, brier_50_values),
                ("probability_of_doubling", lambda value: value >= 1.0, brier_double_values),
            ]:
                probability = num(row.get(probability_field))
                score = brier(probability, [event(value) for value in outcomes]) if probability is not None else None
                if score is not None:
                    target.append(score)
        group_rows.append({
            "horizon_days": horizon,
            "explicit_method_id": method,
            "forecast_rows": len(rows),
            "realized_outcomes": len(realized),
            "realized_median_return": round(median(realized), 6) if realized else "",
            "interval_10_90_coverage": round(mean(coverage_10_90), 6) if coverage_10_90 else "",
            "brier_loss": round(mean(brier_loss_values), 6) if brier_loss_values else "",
            "brier_50pct_gain": round(mean(brier_50_values), 6) if brier_50_values else "",
            "brier_doubling": round(mean(brier_double_values), 6) if brier_double_values else "",
            "validation_status": "SUFFICIENT_GROUP_EVIDENCE" if len(realized) >= int(contract["historical_validation"]["minimum_group_outcomes_for_metric"]) else "INSUFFICIENT_GROUP_EVIDENCE",
        })

    horizon_rows: list[dict[str, Any]] = []
    for horizon in contract["required_horizons_days"]:
        subset = [row for row in group_rows if row["horizon_days"] == horizon]
        horizon_rows.append({
            "horizon_days": horizon,
            "method_groups": len(subset),
            "forecast_rows": sum(int(row["forecast_rows"]) for row in subset),
            "realized_outcomes": sum(int(row["realized_outcomes"]) for row in subset),
            "sufficient_method_groups": sum(row["validation_status"] == "SUFFICIENT_GROUP_EVIDENCE" for row in subset),
        })

    product_rows: list[dict[str, Any]] = []
    for cid, rows in sorted(by_product.items()):
        statuses = Counter(row["calibration_status"] for row in rows)
        if statuses["BLOCKED"]:
            product_status = "BLOCKED"
        elif statuses["REASONABLENESS_REVIEW_REQUIRED"]:
            product_status = "REASONABLENESS_REVIEW_REQUIRED"
        elif statuses["CALIBRATED"] == len(rows):
            product_status = "CALIBRATED"
        elif statuses["CALIBRATED"] + statuses["CALIBRATED_WITH_LIMITATIONS"] == len(rows):
            product_status = "CALIBRATED_WITH_LIMITATIONS"
        else:
            product_status = "INSUFFICIENT_REALIZED_VALIDATION"
        product_rows.append({
            "canonical_product_id": cid,
            "product_name": rows[0]["product_name"],
            "forecast_rows": len(rows),
            "calibrated_rows": statuses["CALIBRATED"],
            "limited_rows": statuses["CALIBRATED_WITH_LIMITATIONS"],
            "review_rows": statuses["REASONABLENESS_REVIEW_REQUIRED"],
            "insufficient_rows": statuses["INSUFFICIENT_REALIZED_VALIDATION"],
            "blocked_rows": statuses["BLOCKED"],
            "product_calibration_status": product_status,
        })

    lorwyn_rows = [row for row in row_audit if norm(row["product_name"]) == norm("Lorwyn Eclipsed - Collector Booster Display")]
    invalid_rows = [row for row in row_audit if row["calibration_status"] == "BLOCKED"]
    if len(forecasts) != int(contract["required_forecast_rows"]):
        failures.append(f"FORECAST_ROW_COUNT:{len(forecasts)}")
    if len({clean(row["canonical_product_id"]) for row in forecasts}) != int(contract["required_forecast_products"]):
        failures.append("FORECAST_PRODUCT_COUNT")
    if len(keys) != int(contract["required_forecast_rows"]) or any(count != 1 for count in keys.values()):
        failures.append("DUPLICATE_PRODUCT_HORIZON_KEYS")
    if len(lineage) != int(contract["required_lineage_rows"]) or open_lineage:
        failures.append("LINEAGE_NOT_CLOSED")
    if invalid_rows:
        failures.append(f"STRUCTURALLY_INVALID_FORECAST_ROWS:{len(invalid_rows)}")
    if any(row["calibration_status"] not in contract["allowed_row_statuses"] for row in row_audit):
        failures.append("UNCLASSIFIED_FORECAST_ROWS")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_final_forecast_row_validation.csv", row_audit)
    write_csv(OUTPUT / "collector_probability_calibration_by_horizon.csv", horizon_rows)
    write_csv(OUTPUT / "collector_probability_calibration_by_method.csv", group_rows)
    write_csv(OUTPUT / "collector_historical_interval_coverage.csv", group_rows)
    write_csv(OUTPUT / "collector_horizon_coherence_audit.csv", coherence_rows)
    write_csv(OUTPUT / "collector_extreme_forecast_review_queue.csv", extreme_rows)
    write_csv(OUTPUT / "collector_product_calibration_status.csv", product_rows)
    write_csv(OUTPUT / "collector_lorwyn_reasonableness_review.csv", lorwyn_rows)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_FINAL_PROBABILISTIC_CALIBRATION_AND_REASONABLENESS_CERTIFICATION"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "forecast_products_inspected": len({row["canonical_product_id"] for row in row_audit}),
        "forecast_rows_inspected": len(row_audit),
        "unique_product_horizon_keys": len(keys),
        "invalid_structural_rows": len(invalid_rows),
        "reasonableness_review_rows": sum(row["calibration_status"] == "REASONABLENESS_REVIEW_REQUIRED" for row in row_audit),
        "insufficient_realized_validation_rows": sum(row["calibration_status"] == "INSUFFICIENT_REALIZED_VALIDATION" for row in row_audit),
        "calibrated_rows": sum(row["calibration_status"] == "CALIBRATED" for row in row_audit),
        "calibrated_with_limitations_rows": sum(row["calibration_status"] == "CALIBRATED_WITH_LIMITATIONS" for row in row_audit),
        "coherence_review_pairs": sum(bool(row["review_required"]) for row in coherence_rows),
        "extreme_review_queue_rows": len(extreme_rows),
        "lorwyn_review_rows": len(lorwyn_rows),
        "lineage_rows": len(lineage),
        "lineage_open_rows": len(open_lineage),
        "forecast_authority_sha256": sha256(paths["final_forecasts"]),
        "lineage_authority_sha256": sha256(paths["forecast_lineage"]),
        "forecast_values_modified": False,
        "production_forecast_authorized": False,
        "ranking_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_probabilistic_calibration_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
