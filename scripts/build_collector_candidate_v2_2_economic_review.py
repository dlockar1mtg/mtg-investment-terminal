from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_v2_2_economic_review_v1.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def projected_price(price: float | None, annual_rate: float | None, years: int) -> float | None:
    if price is None or annual_rate is None or annual_rate <= -1:
        return None
    return float(price * ((1 + annual_rate) ** years))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    candidate_root = ROOT / cfg["inputs"]["candidate_root"]
    out = ROOT / cfg["output_directory"]
    source = candidate_root / "collector_candidate_methodology_v2_2_forecasts.csv"
    if not source.exists():
        result = {"status": "FAIL", "failure_count": 1, "failures": [f"missing_input:{source}"]}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(source, low_memory=False)
    thresholds = cfg["thresholds"]
    rows = []
    for _, row in forecasts.iterrows():
        out_row = row.to_dict()
        price = num(row.get("current_price"))
        rate = num(row.get("candidate_v2_2_base_annual_rate"))
        downside = num(row.get("candidate_v2_2_downside_annual_rate"))
        upside = num(row.get("candidate_v2_2_upside_annual_rate"))
        confidence = num(row.get("confidence_score"))
        one = projected_price(price, rate, 1)
        three = projected_price(price, rate, 3)
        five = projected_price(price, rate, 5)
        multiple = None if price in {None, 0} or five is None else five / price
        flags = {
            "high_rate_review_required": bool(rate is not None and abs(rate) >= thresholds["high_absolute_annual_rate"]),
            "extreme_rate_review_required": bool(rate is not None and abs(rate) >= thresholds["extreme_absolute_annual_rate"]),
            "negative_downside_review_required": bool(downside is not None and downside < thresholds["negative_downside_rate"]),
            "five_year_multiple_review_required": bool(multiple is not None and multiple > thresholds["maximum_five_year_price_multiple"]),
            "low_confidence_review_required": bool(confidence is not None and confidence < thresholds["minimum_confidence_for_review"]),
            "reverse_score_review_required": str(row.get("candidate_v2_2_method_status", "")).startswith("DIAGNOSTIC_ONLY_REVERSE_SCORE"),
            "inactive_formula_review_required": str(row.get("candidate_v2_2_method_status", "")) == "FORMULA_INACTIVE_OWNER_DECISION",
        }
        review_required = any(flags.values())
        out_row.update({
            "projected_price_1y": one,
            "projected_price_3y": three,
            "projected_price_5y": five,
            "projected_price_5y_multiple": multiple,
            **flags,
            "economic_review_required": review_required,
            "economic_review_status": "REVIEW_REQUIRED" if review_required else "NO_THRESHOLD_FLAG",
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
            "automatic_model_update_allowed": False,
        })
        rows.append(out_row)

    product = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    product.to_csv(out / "collector_candidate_v2_2_economic_product_review.csv", index=False)

    route = product.groupby("forecast_method_route", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        complete_count=("candidate_v2_2_calculation_complete", lambda s: int(s.map(truthy).sum())),
        mean_candidate_rate=("candidate_v2_2_base_annual_rate", "mean"),
        median_candidate_rate=("candidate_v2_2_base_annual_rate", "median"),
        minimum_candidate_rate=("candidate_v2_2_base_annual_rate", "min"),
        maximum_candidate_rate=("candidate_v2_2_base_annual_rate", "max"),
        economic_review_required_count=("economic_review_required", lambda s: int(s.map(truthy).sum())),
        high_rate_review_count=("high_rate_review_required", lambda s: int(s.map(truthy).sum())),
        extreme_rate_review_count=("extreme_rate_review_required", lambda s: int(s.map(truthy).sum())),
        negative_downside_review_count=("negative_downside_review_required", lambda s: int(s.map(truthy).sum())),
        five_year_multiple_review_count=("five_year_multiple_review_required", lambda s: int(s.map(truthy).sum())),
    ).reset_index()
    route.to_csv(out / "collector_candidate_v2_2_economic_route_summary.csv", index=False)

    flagged = product[product["economic_review_required"].map(truthy)].copy()
    flagged.to_csv(out / "collector_candidate_v2_2_economic_review_queue.csv", index=False)

    summary = {
        "audit_name": "Collector Candidate v2.2 Economic Reasonableness Review",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(product)),
        "complete_count": int(product["candidate_v2_2_calculation_complete"].map(truthy).sum()),
        "route_count": int(product["forecast_method_route"].nunique()),
        "economic_review_required_count": int(product["economic_review_required"].map(truthy).sum()),
        "high_rate_review_count": int(product["high_rate_review_required"].map(truthy).sum()),
        "extreme_rate_review_count": int(product["extreme_rate_review_required"].map(truthy).sum()),
        "negative_downside_review_count": int(product["negative_downside_review_required"].map(truthy).sum()),
        "five_year_multiple_review_count": int(product["five_year_multiple_review_required"].map(truthy).sum()),
        "reverse_score_review_count": int(product["reverse_score_review_required"].map(truthy).sum()),
        "inactive_formula_review_count": int(product["inactive_formula_review_required"].map(truthy).sum()),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "governing_note": "This batch reviews Candidate v2.2 economic reasonableness, projection magnitudes, scenario direction, and review thresholds. It does not certify accuracy or authorize forecasts or purchases.",
        "failure_count": 0,
        "failures": [],
    }
    if len(product) != 51 or summary["complete_count"] != 50 or summary["route_count"] != 4:
        summary["status"] = "FAIL"
        summary["failure_count"] = 1
        summary["failures"] = ["structural_expectation_failed"]
    (out / "collector_candidate_v2_2_economic_review_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
