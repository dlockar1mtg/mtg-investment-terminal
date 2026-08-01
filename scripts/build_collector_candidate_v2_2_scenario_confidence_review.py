from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_v2_2_scenario_confidence_review_v1.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def clip(value: float, low: float, high: float) -> float:
    return float(min(max(value, low), high))


def first_num(row: pd.Series, names: list[str]) -> float | None:
    for name in names:
        if name in row.index:
            value = num(row.get(name))
            if value is not None:
                return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    roots = {name: ROOT / value for name, value in cfg["inputs"].items()}
    out = ROOT / cfg["output_directory"]
    paths = {
        "candidate": roots["candidate_root"] / "collector_candidate_methodology_v2_2_forecasts.csv",
        "economic": roots["economic_root"] / "collector_candidate_v2_2_economic_product_review.csv",
        "outcomes": roots["evidence_root"] / "collector_retrospective_outcome_diagnostics.csv",
        "sensitivity": roots["sensitivity_root"] / "collector_methodology_sensitivity_product_review.csv",
    }
    missing = [f"missing_input:{k}:{v}" for k, v in paths.items() if not v.exists()]
    if missing:
        result = {"status": "FAIL", "failure_count": len(missing), "failures": missing}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    candidate = pd.read_csv(paths["candidate"], low_memory=False)
    economic = pd.read_csv(paths["economic"], low_memory=False)
    outcomes = pd.read_csv(paths["outcomes"], low_memory=False)
    sensitivity = pd.read_csv(paths["sensitivity"], low_memory=False)
    pid = "canonical_tcgplayer_product_id"
    for frame in [candidate, economic, outcomes, sensitivity]:
        if pid in frame.columns:
            frame[pid] = frame[pid].astype(str).str.replace(r"\.0$", "", regex=True)

    outcome_cols = [c for c in [pid, "annualized_volatility", "volatility", "maximum_drawdown", "max_drawdown", "observation_count"] if c in outcomes.columns]
    sens_cols = [c for c in [pid, "variant_spread", "high_peer_concentration_flag", "short_history_flag", "reverse_pair_candidate_used"] if c in sensitivity.columns]
    merged = candidate.merge(outcomes[outcome_cols].drop_duplicates(pid), on=pid, how="left", suffixes=("", "_outcome"))
    merged = merged.merge(sensitivity[sens_cols].drop_duplicates(pid), on=pid, how="left", suffixes=("", "_sensitivity"))

    p = cfg["diagnostic_parameters"]
    rows = []
    variants = []
    for _, row in merged.iterrows():
        route = str(row.get("forecast_method_route", ""))
        base = num(row.get("candidate_v2_2_base_annual_rate"))
        inherited = num(row.get("uncertainty_width"))
        volatility = first_num(row, ["annualized_volatility", "volatility"])
        drawdown = first_num(row, ["maximum_drawdown", "max_drawdown"])
        spread = num(row.get("variant_spread"))
        peer_count = first_num(row, ["peer_count_after_trim", "comparable_peer_count", "peer_count"])
        reverse = truthy(row.get("reverse_pair_candidate_used")) or str(row.get("candidate_v2_2_method_status", "")).startswith("DIAGNOSTIC_ONLY_REVERSE_SCORE")
        short = truthy(row.get("short_history_flag")) or route == "DIRECT_HISTORY_LIMITED"
        concentration = truthy(row.get("high_peer_concentration_flag"))

        floor = float(p["minimum_width_by_route"].get(route, 0.25))
        cap = float(p["maximum_width_by_route"].get(route, 1.00))
        vol_width = None if volatility is None else abs(volatility)
        spread_width = None if spread is None else abs(spread) / 2.0
        components = [v for v in [floor, vol_width, spread_width] if v is not None and np.isfinite(v)]
        evidence_raw = max(components) if components else floor
        evidence_bounded = clip(evidence_raw, floor, cap)
        downside_floor_width = None if base is None else max(0.0, base - float(p["maximum_downside_annual_rate"]))
        bounded_loss_width = evidence_bounded if downside_floor_width is None else min(evidence_bounded, downside_floor_width)

        confidence = float(p["confidence_route_base"].get(route, 0.30))
        if peer_count is not None:
            confidence += min(peer_count, 25.0) / 25.0 * 0.10
        if volatility is not None:
            confidence -= min(abs(volatility), 2.0) / 2.0 * 0.15
        if spread is not None:
            confidence -= min(abs(spread), 1.0) * 0.15
        if reverse:
            confidence -= 0.20
        if short:
            confidence -= 0.10
        if concentration:
            confidence -= 0.10
        diagnostic_confidence = clip(confidence, float(p["confidence_minimum"]), float(p["confidence_maximum"]))

        inherited_down = None if base is None or inherited is None else base - inherited
        inherited_up = None if base is None or inherited is None else base + inherited
        bounded_down = None if base is None else base - bounded_loss_width
        bounded_up = None if base is None else base + bounded_loss_width
        inherited_invalid = bool(inherited is not None and (inherited < 0 or inherited > 2.0))
        downside_below_loss_floor = bool(inherited_down is not None and inherited_down < float(p["maximum_downside_annual_rate"]))
        width_review = inherited_invalid or downside_below_loss_floor or (inherited is not None and abs(inherited - bounded_loss_width) >= 0.25)
        confidence_review = bool(num(row.get("confidence_score")) is None or abs((num(row.get("confidence_score")) or 0.0) - diagnostic_confidence) >= 0.20)

        out_row = row.to_dict()
        out_row.update({
            "inherited_uncertainty_width": inherited,
            "inherited_downside_annual_rate": inherited_down,
            "inherited_upside_annual_rate": inherited_up,
            "retrospective_volatility_component": volatility,
            "retrospective_drawdown_component": drawdown,
            "methodology_spread_component": spread,
            "diagnostic_evidence_width_raw": evidence_raw,
            "diagnostic_evidence_width_bounded": evidence_bounded,
            "diagnostic_loss_bounded_width": bounded_loss_width,
            "diagnostic_downside_annual_rate": bounded_down,
            "diagnostic_upside_annual_rate": bounded_up,
            "diagnostic_confidence_score": diagnostic_confidence,
            "inherited_width_invalid": inherited_invalid,
            "inherited_downside_below_loss_floor": downside_below_loss_floor,
            "scenario_width_review_required": width_review,
            "confidence_review_required": confidence_review,
            "scenario_methodology_authorized": False,
            "confidence_methodology_authorized": False,
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
            "automatic_model_update_allowed": False,
        })
        rows.append(out_row)
        for name, width in {
            "INHERITED": inherited,
            "RETROSPECTIVE_VOLATILITY": vol_width,
            "HALF_METHODOLOGY_SPREAD": spread_width,
            "EVIDENCE_MAX_BOUNDED": evidence_bounded,
            "LOSS_BOUNDED_EVIDENCE": bounded_loss_width,
        }.items():
            variants.append({
                pid: row.get(pid),
                "product_name": row.get("product_name", ""),
                "forecast_method_route": route,
                "variant_name": name,
                "variant_width": width,
                "variant_downside_rate": None if base is None or width is None else base - width,
                "variant_upside_rate": None if base is None or width is None else base + width,
                "diagnostic_only": True,
            })

    product = pd.DataFrame(rows)
    variant = pd.DataFrame(variants)
    out.mkdir(parents=True, exist_ok=True)
    product.to_csv(out / "collector_candidate_v2_2_scenario_confidence_product_review.csv", index=False)
    variant.to_csv(out / "collector_candidate_v2_2_scenario_width_variants.csv", index=False)

    route = product.groupby("forecast_method_route", dropna=False).agg(
        product_count=(pid, "count"),
        complete_count=("candidate_v2_2_calculation_complete", lambda s: int(s.map(truthy).sum())),
        mean_inherited_width=("inherited_uncertainty_width", "mean"),
        median_inherited_width=("inherited_uncertainty_width", "median"),
        mean_diagnostic_width=("diagnostic_loss_bounded_width", "mean"),
        median_diagnostic_width=("diagnostic_loss_bounded_width", "median"),
        mean_diagnostic_confidence=("diagnostic_confidence_score", "mean"),
        scenario_width_review_count=("scenario_width_review_required", lambda s: int(s.map(truthy).sum())),
        confidence_review_count=("confidence_review_required", lambda s: int(s.map(truthy).sum())),
    ).reset_index()
    route.to_csv(out / "collector_candidate_v2_2_scenario_confidence_route_summary.csv", index=False)

    queue = product[product["scenario_width_review_required"].map(truthy) | product["confidence_review_required"].map(truthy)].copy()
    queue.to_csv(out / "collector_candidate_v2_2_scenario_confidence_review_queue.csv", index=False)

    summary = {
        "audit_name": "Collector Candidate v2.2 Scenario and Confidence Review",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(product)),
        "complete_count": int(product["candidate_v2_2_calculation_complete"].map(truthy).sum()),
        "route_count": int(product["forecast_method_route"].nunique()),
        "variant_row_count": int(len(variant)),
        "scenario_width_review_count": int(product["scenario_width_review_required"].map(truthy).sum()),
        "confidence_review_count": int(product["confidence_review_required"].map(truthy).sum()),
        "inherited_downside_below_loss_floor_count": int(product["inherited_downside_below_loss_floor"].map(truthy).sum()),
        "scenario_methodology_authorized": False,
        "confidence_methodology_authorized": False,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "governing_note": "This batch compares inherited scenario widths and confidence scores with diagnostic evidence-based alternatives. It does not select, activate, or authorize a replacement methodology.",
        "failure_count": 0,
        "failures": [],
    }
    if len(product) != 51 or summary["complete_count"] != 50 or summary["route_count"] != 4 or len(variant) != 255:
        summary["status"] = "FAIL"
        summary["failure_count"] = 1
        summary["failures"] = ["structural_expectation_failed"]
    (out / "collector_candidate_v2_2_scenario_confidence_review_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
