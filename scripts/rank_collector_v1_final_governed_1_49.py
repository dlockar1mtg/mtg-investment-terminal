from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_governed_ranking_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_final_governed_ranking"


def clean(value: Any) -> str:
    return str(value or "").strip()


def num(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
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


def percentile(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    count = len(ordered)
    if count <= 1:
        return {key: 100.0 for key in values}
    ranks: dict[str, float] = {}
    for index, (key, _) in enumerate(ordered):
        score = 100.0 * index / (count - 1)
        ranks[key] = score if higher_is_better else 100.0 - score
    return ranks


def field(row: dict[str, str], candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate in row:
            return clean(row.get(candidate))
    return ""


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    paths = {name: ROOT / relative for name, relative in contract["authorities"].items()}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_AUTHORITY:" + ";".join(missing))

    forecasts = read_csv(paths["final_forecasts"])
    eligibility = read_csv(paths["final_ranking_eligibility"])
    eligibility_summary = json.loads(paths["final_ranking_eligibility_summary"].read_text(encoding="utf-8"))
    calibration = read_csv(paths["calibration_rows"])
    supply = read_csv(paths["current_supply"])
    failures: list[str] = []

    if eligibility_summary.get("status") != "PASS_COLLECTOR_FINAL_RANKING_ELIGIBILITY_CERTIFICATION":
        failures.append("FINAL_RANKING_ELIGIBILITY_NOT_PASS")
    if eligibility_summary.get("ranking_execution_authorized") is not True:
        failures.append("RANKING_EXECUTION_NOT_AUTHORIZED")
    if len(forecasts) != int(contract["required_forecast_rows"]):
        failures.append(f"FORECAST_ROW_COUNT:{len(forecasts)}")
    if len(eligibility) != int(contract["required_products"]):
        failures.append(f"ELIGIBILITY_PRODUCT_COUNT:{len(eligibility)}")

    forecast_by_key = {
        (clean(row.get("canonical_product_id")), int(float(clean(row.get("horizon_days")) or 0))): row
        for row in forecasts
    }
    calibration_by_key = {
        (clean(row.get("canonical_product_id")), int(float(clean(row.get("horizon_days")) or 0))): row
        for row in calibration
    }
    supply_by_id = {clean(row.get("canonical_product_id")): row for row in supply}

    raw: dict[str, dict[str, Any]] = {}
    for eligible in eligibility:
        cid = clean(eligible.get("canonical_product_id"))
        row365 = forecast_by_key.get((cid, 365))
        row1095 = forecast_by_key.get((cid, 1095))
        if row365 is None or row1095 is None:
            failures.append(f"PRIMARY_HORIZON_FORECAST_MISSING:{cid}")
            continue

        current_price = num(row365.get("current_price"))
        median365 = num(row365.get("median_price"))
        median1095 = num(row1095.get("median_price"))
        p10_365 = num(row365.get("p10_price"))
        p90_365 = num(row365.get("p90_price"))
        prob_loss_365 = num(row365.get("probability_of_loss"))
        prob_50_365 = num(row365.get("probability_of_50pct_gain"))
        prob_double_365 = num(row365.get("probability_of_doubling"))
        if None in (current_price, median365, median1095, p10_365, p90_365, prob_loss_365, prob_50_365, prob_double_365):
            failures.append(f"PRIMARY_HORIZON_VALUE_MISSING:{cid}")
            continue
        if current_price <= 0:
            failures.append(f"INVALID_CURRENT_PRICE:{cid}")
            continue

        return365 = median365 / current_price - 1.0
        return1095 = median1095 / current_price - 1.0
        annualized1095 = (1.0 + return1095) ** (365.0 / 1095.0) - 1.0 if return1095 > -1.0 else -1.0
        downside = 1.0 - prob_loss_365
        early = 0.7 * prob_50_365 + 0.3 * prob_double_365
        interval_width = (p90_365 - p10_365) / current_price
        uncertainty_control = 1.0 / (1.0 + max(0.0, interval_width))

        supply_row = supply_by_id.get(cid, {})
        listing_count = num(field(supply_row, ["accepted_listing_count", "listing_count", "active_listing_count"])) or 0.0
        seller_count = num(field(supply_row, ["distinct_seller_count", "seller_count"])) or 0.0
        supply_depth = math.log1p(listing_count) + 0.5 * math.log1p(seller_count)

        cal365 = clean(calibration_by_key.get((cid, 365), {}).get("calibration_status"))
        cal1095 = clean(calibration_by_key.get((cid, 1095), {}).get("calibration_status"))
        calibration_points = {
            "CALIBRATED": 1.0,
            "CALIBRATED_WITH_LIMITATIONS": 0.75,
            "INSUFFICIENT_REALIZED_VALIDATION": 0.35,
            "REASONABLENESS_REVIEW_REQUIRED": 0.15,
            "BLOCKED": 0.0,
        }
        calibration_strength = 0.6 * calibration_points.get(cal365, 0.0) + 0.4 * calibration_points.get(cal1095, 0.0)

        penalty = num(eligible.get("ranking_penalty_points")) or 0.0
        raw[cid] = {
            "canonical_product_id": cid,
            "product_name": clean(eligible.get("product_name")),
            "current_price": current_price,
            "median_return_365": return365,
            "median_return_1095": return1095,
            "annualized_return_1095": annualized1095,
            "probability_of_loss_365": prob_loss_365,
            "probability_of_50pct_gain_365": prob_50_365,
            "probability_of_doubling_365": prob_double_365,
            "interval_width_return_365": interval_width,
            "raw_early_opportunity": early,
            "raw_downside_protection": downside,
            "raw_uncertainty_control": uncertainty_control,
            "accepted_listing_count": listing_count,
            "distinct_seller_count": seller_count,
            "raw_supply_demand": supply_depth,
            "calibration_status_365": cal365,
            "calibration_status_1095": cal1095,
            "raw_calibration_strength": calibration_strength,
            "final_ranking_eligibility_status": clean(eligible.get("final_ranking_eligibility_status")),
            "ranking_penalty_points": penalty,
            "purchase_eligible_at_this_stage": clean(eligible.get("purchase_eligible_at_this_stage")),
            "limitations": clean(eligible.get("limitations")),
        }

    if len(raw) != int(contract["required_products"]):
        failures.append(f"SCORABLE_PRODUCT_COUNT:{len(raw)}")

    factors = {
        "forecast_return_365": percentile({cid: row["median_return_365"] for cid, row in raw.items()}),
        "forecast_return_1095_annualized": percentile({cid: row["annualized_return_1095"] for cid, row in raw.items()}),
        "early_opportunity": percentile({cid: row["raw_early_opportunity"] for cid, row in raw.items()}),
        "downside_protection": percentile({cid: row["raw_downside_protection"] for cid, row in raw.items()}),
        "uncertainty_control": percentile({cid: row["raw_uncertainty_control"] for cid, row in raw.items()}),
        "supply_demand": percentile({cid: row["raw_supply_demand"] for cid, row in raw.items()}),
        "calibration_strength": percentile({cid: row["raw_calibration_strength"] for cid, row in raw.items()}),
    }

    weights = contract["weights"]
    ranking_rows: list[dict[str, Any]] = []
    for cid, row in raw.items():
        weighted = sum(float(weights[name]) * factors[name][cid] for name in weights)
        final_score = weighted - float(row["ranking_penalty_points"])
        ranking_rows.append({
            **row,
            **{f"factor_{name}": round(factors[name][cid], 6) for name in factors},
            "weighted_score_before_penalty": round(weighted, 6),
            "final_governed_score": round(final_score, 6),
            "ranking_authorized": True,
            "purchase_recommendations_authorized": False,
            "forecast_values_modified": False,
        })

    ranking_rows.sort(key=lambda row: (-float(row["final_governed_score"]), row["canonical_product_id"]))
    for index, row in enumerate(ranking_rows, start=1):
        row["final_rank"] = index
        row["rank_tier"] = "TIER_1" if index <= 10 else ("TIER_2" if index <= 25 else "TIER_3")

    if [row["final_rank"] for row in ranking_rows] != list(range(1, int(contract["required_products"]) + 1)):
        failures.append("RANK_SEQUENCE_INVALID")
    if len({row["canonical_product_id"] for row in ranking_rows}) != len(ranking_rows):
        failures.append("DUPLICATE_RANKED_PRODUCT")
    if any(row["forecast_values_modified"] for row in ranking_rows):
        failures.append("FORECAST_VALUES_MODIFIED")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_final_governed_1_49_rankings.csv", ranking_rows)
    write_csv(OUTPUT / "collector_final_ranking_factor_audit.csv", ranking_rows)
    write_csv(OUTPUT / "collector_top_10_investment_candidates.csv", ranking_rows[:10])

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_FINAL_GOVERNED_1_49_RANKING"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "products_ranked": len(ranking_rows),
        "forecast_rows_referenced": len(forecasts),
        "top_ranked_product": ranking_rows[0]["product_name"] if ranking_rows else "",
        "conditional_products_ranked": sum(row["final_ranking_eligibility_status"] == "CONDITIONAL_RANKING_ELIGIBLE" for row in ranking_rows),
        "purchase_ineligible_products_ranked": sum(clean(row["purchase_eligible_at_this_stage"]).lower() != "true" for row in ranking_rows),
        "forecast_values_modified": False,
        "ranking_authorized": not failures,
        "purchase_recommendations_authorized": False,
        "authority_hashes": {name: sha256(path) for name, path in paths.items()},
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_final_governed_ranking_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("\nTOP 10")
    for row in ranking_rows[:10]:
        print({
            "rank": row["final_rank"],
            "product_name": row["product_name"],
            "score": row["final_governed_score"],
            "return_365": round(row["median_return_365"], 6),
            "prob_50_gain_365": row["probability_of_50pct_gain_365"],
            "prob_loss_365": row["probability_of_loss_365"],
            "penalty": row["ranking_penalty_points"],
        })
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
