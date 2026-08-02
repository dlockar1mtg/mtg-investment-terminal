from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_purchase_recommendation_certification_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_purchase_recommendation_certification"


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


def truthy(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes"}


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


def budget_band(price: float, bands: list[dict[str, Any]]) -> str:
    for band in bands:
        maximum = band.get("maximum_price")
        if maximum is None or price <= float(maximum):
            return clean(band.get("label"))
    return "UNCLASSIFIED"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    paths = {name: ROOT / relative for name, relative in contract["authorities"].items()}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_AUTHORITY:" + ";".join(missing))

    rankings = read_csv(paths["final_rankings"])
    ranking_summary = json.loads(paths["ranking_summary"].read_text(encoding="utf-8"))
    forecasts = read_csv(paths["final_forecasts"])
    eligibility = read_csv(paths["ranking_eligibility"])
    current_authority = read_csv(paths["current_price_authority"])
    failures: list[str] = []

    if ranking_summary.get("status") != "PASS_COLLECTOR_FINAL_GOVERNED_1_49_RANKING":
        failures.append("FINAL_RANKING_NOT_PASS")
    if ranking_summary.get("ranking_authorized") is not True:
        failures.append("RANKING_NOT_AUTHORIZED")
    if len(rankings) != int(contract["required_ranked_products"]):
        failures.append(f"RANKED_PRODUCT_COUNT:{len(rankings)}")

    forecast365 = {
        clean(row.get("canonical_product_id")): row
        for row in forecasts
        if int(float(clean(row.get("horizon_days")) or 0)) == int(contract["primary_horizon_days"])
    }
    eligibility_by_id = {clean(row.get("canonical_product_id")): row for row in eligibility}
    authority_by_id = {clean(row.get("canonical_product_id")): row for row in current_authority}
    rules = contract["entry_rules"]

    rows: list[dict[str, Any]] = []
    for ranking in rankings:
        cid = clean(ranking.get("canonical_product_id"))
        forecast = forecast365.get(cid)
        eligible = eligibility_by_id.get(cid)
        authority = authority_by_id.get(cid)
        row_failures: list[str] = []
        if forecast is None:
            row_failures.append("MISSING_365_FORECAST")
        if eligible is None:
            row_failures.append("MISSING_ELIGIBILITY_ROW")
        if authority is None:
            row_failures.append("MISSING_CURRENT_PRICE_AUTHORITY")

        rank = int(float(clean(ranking.get("final_rank")) or 0))
        score = num(ranking.get("final_governed_score"))
        current_price = num(ranking.get("current_price"))
        authority_price = num(authority.get("current_price")) if authority else None
        p25 = num(forecast.get("p25_price")) if forecast else None
        median = num(forecast.get("median_price")) if forecast else None
        p90 = num(forecast.get("p90_price")) if forecast else None
        prob_loss = num(ranking.get("probability_of_loss_365"))
        prob_50 = num(ranking.get("probability_of_50pct_gain_365"))
        prob_double = num(ranking.get("probability_of_doubling_365"))
        purchase_stage_eligible = truthy(eligible.get("purchase_eligible_at_this_stage")) if eligible else False
        conditional = clean(eligible.get("final_ranking_eligibility_status")) == "CONDITIONAL_RANKING_ELIGIBLE" if eligible else True

        if current_price is None or authority_price is None or abs(current_price - authority_price) > 0.01:
            row_failures.append("CURRENT_PRICE_AUTHORITY_MISMATCH")
        if None in (score, current_price, p25, median, p90, prob_loss, prob_50, prob_double):
            row_failures.append("REQUIRED_PURCHASE_INPUT_MISSING")

        strong_ceiling = p25 / (1.0 + float(rules["p25_required_upside_strong"])) if p25 else None
        candidate_ceiling = p25 / (1.0 + float(rules["p25_required_upside_candidate"])) if p25 else None
        status = "WATCHLIST"
        basis = "DOES_NOT_CLEAR_PURCHASE_THRESHOLDS"
        recommendation_authorized = False

        if row_failures:
            status = "BLOCKED"
            basis = "|".join(row_failures)
        elif conditional or not purchase_stage_eligible:
            status = "NOT_PURCHASE_ELIGIBLE"
            basis = "CONDITIONAL_OR_INELIGIBLE_EVIDENCE_STATUS"
        elif (
            rank <= int(rules["strong_candidate_max_rank"])
            and score >= float(rules["strong_candidate_min_score"])
            and prob_loss <= float(rules["strong_candidate_max_loss_probability"])
            and prob_50 >= float(rules["strong_candidate_min_50pct_gain_probability"])
            and current_price <= strong_ceiling
        ):
            status = "STRONG_PURCHASE_CANDIDATE"
            basis = "TOP_TIER_SCORE_DOWNSIDE_AND_P25_ENTRY_MARGIN"
            recommendation_authorized = True
        elif (
            rank <= int(rules["candidate_max_rank"])
            and score >= float(rules["candidate_min_score"])
            and prob_loss <= float(rules["candidate_max_loss_probability"])
            and current_price <= candidate_ceiling
        ):
            status = "PURCHASE_CANDIDATE"
            basis = "RANK_SCORE_DOWNSIDE_AND_P25_ENTRY_CLEAR"
            recommendation_authorized = True

        rows.append({
            "final_rank": rank,
            "canonical_product_id": cid,
            "product_name": clean(ranking.get("product_name")),
            "current_price": current_price,
            "budget_context_band": budget_band(current_price or 0.0, contract["budget_context_bands"]),
            "final_governed_score": score,
            "p25_price_365": p25,
            "median_price_365": median,
            "p90_price_365": p90,
            "strong_entry_ceiling": round(strong_ceiling, 2) if strong_ceiling is not None else "",
            "candidate_entry_ceiling": round(candidate_ceiling, 2) if candidate_ceiling is not None else "",
            "current_vs_strong_ceiling_pct": round(current_price / strong_ceiling - 1.0, 6) if current_price and strong_ceiling else "",
            "median_return_365": num(ranking.get("median_return_365")),
            "probability_of_loss_365": prob_loss,
            "probability_of_50pct_gain_365": prob_50,
            "probability_of_doubling_365": prob_double,
            "final_ranking_eligibility_status": clean(eligible.get("final_ranking_eligibility_status")) if eligible else "",
            "purchase_status": status,
            "purchase_basis": basis,
            "recommendation_authorized": recommendation_authorized,
            "recommended_quantity": 1 if recommendation_authorized else 0,
            "forecast_values_modified": False,
        })

    if len({row["canonical_product_id"] for row in rows}) != len(rows):
        failures.append("DUPLICATE_PURCHASE_PRODUCT")
    if any(row["purchase_status"] == "BLOCKED" for row in rows):
        failures.append("BLOCKED_PURCHASE_ROWS_PRESENT")
    if any(row["final_ranking_eligibility_status"] == "CONDITIONAL_RANKING_ELIGIBLE" and row["recommendation_authorized"] for row in rows):
        failures.append("CONDITIONAL_PRODUCT_AUTHORIZED")
    if any(row["forecast_values_modified"] for row in rows):
        failures.append("FORECAST_VALUES_MODIFIED")

    rows.sort(key=lambda row: int(row["final_rank"]))
    authorized = [row for row in rows if row["recommendation_authorized"]]
    watchlist = [row for row in rows if row["purchase_status"] == "WATCHLIST"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_purchase_recommendation_authority.csv", rows)
    write_csv(OUTPUT / "collector_authorized_purchase_candidates.csv", authorized)
    write_csv(OUTPUT / "collector_purchase_watchlist.csv", watchlist)

    counts = Counter(row["purchase_status"] for row in rows)
    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_PURCHASE_RECOMMENDATION_CERTIFICATION"
    summary = {
        "contract_name": contract["contract_name"],
        "contract_version": contract["contract_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "products_evaluated": len(rows),
        "purchase_status_counts": dict(counts),
        "authorized_purchase_candidates": len(authorized),
        "watchlist_products": len(watchlist),
        "conditional_products_authorized": sum(row["final_ranking_eligibility_status"] == "CONDITIONAL_RANKING_ELIGIBLE" and row["recommendation_authorized"] for row in rows),
        "forecast_values_modified": False,
        "purchase_recommendations_authorized": not failures,
        "automatic_purchase_execution_authorized": False,
        "authority_hashes": {name: sha256(path) for name, path in paths.items()},
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_purchase_recommendation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("\nAUTHORIZED PURCHASE CANDIDATES")
    for row in authorized:
        print({
            "rank": row["final_rank"],
            "product_name": row["product_name"],
            "current_price": row["current_price"],
            "purchase_status": row["purchase_status"],
            "strong_entry_ceiling": row["strong_entry_ceiling"],
            "candidate_entry_ceiling": row["candidate_entry_ceiling"],
            "probability_of_loss_365": row["probability_of_loss_365"],
        })
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
