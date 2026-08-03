from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_methodology_v2_3_approval.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def projected_price(price: float | None, annual_rate: float | None, years: int) -> float | None:
    if price is None or annual_rate is None or annual_rate <= -1:
        return None
    return float(price * ((1.0 + annual_rate) ** years))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    candidate_root = ROOT / cfg["inputs"]["candidate_root"]
    review_root = ROOT / cfg["inputs"]["scenario_review_root"]
    out_dir = ROOT / cfg["output_directory"]
    paths = {
        "candidate": candidate_root / "collector_candidate_methodology_v2_2_forecasts.csv",
        "review": review_root / "collector_candidate_v2_2_scenario_confidence_product_review.csv",
    }
    missing = [f"missing_input:{name}:{path}" for name, path in paths.items() if not path.exists()]
    if missing:
        result = {"status": "FAIL", "failure_count": len(missing), "failures": missing}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    candidate = pd.read_csv(paths["candidate"], low_memory=False)
    review = pd.read_csv(paths["review"], low_memory=False)
    pid = "canonical_tcgplayer_product_id"
    for frame in (candidate, review):
        frame[pid] = frame[pid].astype(str).str.replace(r"\.0$", "", regex=True)

    review_cols = [
        pid,
        "retrospective_volatility_component",
        "methodology_spread_component",
        "diagnostic_confidence_score",
    ]
    merged = candidate.merge(review[review_cols], on=pid, how="left", validate="one_to_one")

    mins = cfg["scenario_decision"]["route_minimum_widths"]
    maxs = cfg["scenario_decision"]["route_maximum_widths"]
    loss_floor = float(cfg["scenario_decision"]["downside_annual_rate_floor"])
    reverse_ceiling = float(cfg["confidence_decision"]["reverse_score_confidence_ceiling"])
    inactive_ceiling = float(cfg["confidence_decision"]["inactive_formula_confidence_ceiling"])

    rows: list[dict[str, object]] = []
    for _, row in merged.iterrows():
        out = row.to_dict()
        route = str(row.get("forecast_method_route", ""))
        rate = num(row.get("candidate_v2_2_base_annual_rate"))
        price = num(row.get("current_price"))
        volatility = num(row.get("retrospective_volatility_component"))
        spread = num(row.get("methodology_spread_component"))
        route_min = float(mins[route])
        route_max = float(maxs[route])

        width_candidates = [route_min]
        if volatility is not None:
            width_candidates.append(abs(volatility))
        if spread is not None:
            width_candidates.append(abs(spread) / 2.0)
        raw_width = max(width_candidates)
        bounded_width = min(max(raw_width, route_min), route_max)

        if rate is None:
            final_width = bounded_width
            downside = None
            upside = None
        else:
            maximum_width_from_loss_floor = rate - loss_floor
            final_width = min(bounded_width, maximum_width_from_loss_floor)
            final_width = max(0.0, final_width)
            downside = max(loss_floor, rate - final_width)
            upside = rate + final_width

        confidence_internal = num(row.get("diagnostic_confidence_score"))
        if confidence_internal is None:
            confidence_internal = 0.0
        confidence_internal = min(max(confidence_internal, 0.0), 1.0)
        confidence_export = confidence_internal * 100.0

        method_status = str(row.get("candidate_v2_2_method_status", ""))
        if method_status.startswith("DIAGNOSTIC_ONLY_REVERSE_SCORE"):
            confidence_export = min(confidence_export, reverse_ceiling)
            confidence_internal = confidence_export / 100.0
        if method_status == "FORMULA_INACTIVE_OWNER_DECISION":
            confidence_export = min(confidence_export, inactive_ceiling)
            confidence_internal = confidence_export / 100.0

        complete = rate is not None
        out.update({
            "candidate_methodology_version": "2.3.0",
            "candidate_v2_3_base_annual_rate": rate,
            "candidate_v2_3_scenario_width_raw": raw_width,
            "candidate_v2_3_scenario_width_bounded": bounded_width,
            "candidate_v2_3_scenario_width_final": final_width,
            "candidate_v2_3_downside_annual_rate": downside,
            "candidate_v2_3_upside_annual_rate": upside,
            "candidate_v2_3_confidence_internal_0_to_1": confidence_internal,
            "candidate_v2_3_confidence_score_0_to_100": confidence_export,
            "candidate_v2_3_projected_price_downside_1y": projected_price(price, downside, 1),
            "candidate_v2_3_projected_price_base_1y": projected_price(price, rate, 1),
            "candidate_v2_3_projected_price_upside_1y": projected_price(price, upside, 1),
            "candidate_v2_3_projected_price_downside_3y": projected_price(price, downside, 3),
            "candidate_v2_3_projected_price_base_3y": projected_price(price, rate, 3),
            "candidate_v2_3_projected_price_upside_3y": projected_price(price, upside, 3),
            "candidate_v2_3_projected_price_downside_5y": projected_price(price, downside, 5),
            "candidate_v2_3_projected_price_base_5y": projected_price(price, rate, 5),
            "candidate_v2_3_projected_price_upside_5y": projected_price(price, upside, 5),
            "candidate_v2_3_method_status": method_status,
            "candidate_v2_3_calculation_complete": complete,
            "scenario_methodology_authorized_for_candidate_v2_3": True,
            "confidence_methodology_authorized_for_candidate_v2_3": True,
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
            "automatic_model_update_allowed": False,
        })
        rows.append(out)

    result = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / "collector_candidate_methodology_v2_3_forecasts.csv", index=False)

    comparison_cols = [
        pid,
        "product_name",
        "forecast_method_route",
        "candidate_v2_2_base_annual_rate",
        "candidate_v2_3_base_annual_rate",
        "candidate_v2_2_downside_annual_rate",
        "candidate_v2_3_downside_annual_rate",
        "candidate_v2_2_upside_annual_rate",
        "candidate_v2_3_upside_annual_rate",
        "confidence_score",
        "candidate_v2_3_confidence_score_0_to_100",
        "candidate_v2_3_scenario_width_final",
        "candidate_v2_3_method_status",
        "candidate_v2_3_calculation_complete",
    ]
    result[comparison_cols].to_csv(out_dir / "collector_candidate_methodology_v2_3_comparison.csv", index=False)

    route_summary = result.groupby("forecast_method_route", dropna=False).agg(
        product_count=(pid, "count"),
        complete_count=("candidate_v2_3_calculation_complete", lambda s: int(s.map(truthy).sum())),
        mean_base_rate=("candidate_v2_3_base_annual_rate", "mean"),
        mean_scenario_width=("candidate_v2_3_scenario_width_final", "mean"),
        minimum_downside_rate=("candidate_v2_3_downside_annual_rate", "min"),
        maximum_upside_rate=("candidate_v2_3_upside_annual_rate", "max"),
        mean_confidence_0_to_100=("candidate_v2_3_confidence_score_0_to_100", "mean"),
    ).reset_index()
    route_summary.to_csv(out_dir / "collector_candidate_methodology_v2_3_route_summary.csv", index=False)

    approval_rows = [
        {
            "decision_id": cfg["scenario_decision"]["decision_id"],
            "owner_decision": cfg["scenario_decision"]["decision"],
            "approval_scope": cfg["scope"],
            "activation_authorized": False,
        },
        {
            "decision_id": cfg["confidence_decision"]["decision_id"],
            "owner_decision": cfg["confidence_decision"]["decision"],
            "approval_scope": cfg["scope"],
            "activation_authorized": False,
        },
    ]
    pd.DataFrame(approval_rows).to_csv(out_dir / "collector_candidate_methodology_v2_3_owner_approval_register.csv", index=False)

    complete_count = int(result["candidate_v2_3_calculation_complete"].map(truthy).sum())
    inactive_count = int((result["candidate_v2_3_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION").sum())
    reverse_count = int(result["candidate_v2_3_method_status"].astype(str).str.startswith("DIAGNOSTIC_ONLY_REVERSE_SCORE").sum())
    downside_floor_violations = int((pd.to_numeric(result["candidate_v2_3_downside_annual_rate"], errors="coerce") < loss_floor - 1e-12).sum())
    reverse_ceiling_violations = int(((result["candidate_v2_3_method_status"].astype(str).str.startswith("DIAGNOSTIC_ONLY_REVERSE_SCORE")) & (pd.to_numeric(result["candidate_v2_3_confidence_score_0_to_100"], errors="coerce") > reverse_ceiling + 1e-12)).sum())
    inactive_ceiling_violations = int(((result["candidate_v2_3_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION") & (pd.to_numeric(result["candidate_v2_3_confidence_score_0_to_100"], errors="coerce") > inactive_ceiling + 1e-12)).sum())

    failures: list[str] = []
    if len(result) != 51:
        failures.append("product_count_not_51")
    if complete_count != 50:
        failures.append("complete_count_not_50")
    if inactive_count != 1:
        failures.append("inactive_hybrid_count_not_1")
    if reverse_count != 7:
        failures.append("reverse_score_count_not_7")
    if downside_floor_violations:
        failures.append("downside_loss_floor_violation")
    if reverse_ceiling_violations:
        failures.append("reverse_confidence_ceiling_violation")
    if inactive_ceiling_violations:
        failures.append("inactive_confidence_ceiling_violation")

    summary = {
        "audit_name": "Collector Candidate Methodology v2.3",
        "audit_version": "2.3.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(result)),
        "complete_count": complete_count,
        "incomplete_count": int(len(result) - complete_count),
        "route_count": int(result["forecast_method_route"].nunique()),
        "japanese_hybrid_inactive_count": inactive_count,
        "reverse_score_diagnostic_only_count": reverse_count,
        "downside_loss_floor_violation_count": downside_floor_violations,
        "reverse_confidence_ceiling_violation_count": reverse_ceiling_violations,
        "inactive_confidence_ceiling_violation_count": inactive_ceiling_violations,
        "scenario_methodology_authorized_for_candidate_v2_3": True,
        "confidence_methodology_authorized_for_candidate_v2_3": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "governing_note": "Candidate v2.3 preserves v2.2 base rates and implements owner-approved route-bounded evidence scenario widths and normalized evidence confidence for development and testing only.",
        "failure_count": len(failures),
        "failures": failures,
    }
    (out_dir / "collector_candidate_methodology_v2_3_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
