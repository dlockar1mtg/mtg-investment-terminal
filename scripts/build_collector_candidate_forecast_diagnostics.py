from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_forecast_diagnostics_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        number = float(text)
        if math.isfinite(number) and number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def weighted_average(values: list[tuple[float, float]]) -> float | None:
    usable = [(v, w) for v, w in values if v is not None and np.isfinite(v) and w > 0]
    if not usable:
        return None
    denominator = sum(w for _, w in usable)
    return sum(v * w for v, w in usable) / denominator if denominator else None


def discover_comparables(search_roots: list[str]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    profiles: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    target_candidates = ["target_investment_product_id", "investment_product_id", "target_product_id", "target_tcgplayer_product_id"]
    peer_candidates = ["comparable_investment_product_id", "comparable_product_id", "peer_product_id", "comparable_tcgplayer_product_id"]
    score_candidates = ["adjusted_similarity_score", "similarity_score", "comparable_score", "selection_score"]

    for root_text in search_roots:
        root = ROOT / root_text
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            if "comparable" not in path.name.lower() and "comparable" not in str(path.parent).lower():
                continue
            try:
                sample = pd.read_csv(path, nrows=5, low_memory=False)
            except Exception as exc:  # noqa: BLE001
                profiles.append({"path": str(path.relative_to(ROOT)).replace("\\", "/"), "readable": False, "error": str(exc)})
                continue
            target = next((c for c in target_candidates if c in sample.columns), None)
            peer = next((c for c in peer_candidates if c in sample.columns), None)
            score = next((c for c in score_candidates if c in sample.columns), None)
            usable = bool(target and peer and score)
            profiles.append({
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "readable": True,
                "target_column": target or "",
                "peer_column": peer or "",
                "score_column": score or "",
                "candidate_usable": usable,
                "error": "",
            })
            if not usable:
                continue
            frame = pd.read_csv(path, low_memory=False)
            frame = frame.rename(columns={target: "target_id_raw", peer: "peer_id_raw", score: "similarity_score_raw"})
            frame["target_id"] = frame["target_id_raw"].map(norm_id)
            frame["peer_id"] = frame["peer_id_raw"].map(norm_id)
            frame["similarity_score"] = pd.to_numeric(frame["similarity_score_raw"], errors="coerce")
            frame["comparable_source_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
            frames.append(frame[["target_id", "peer_id", "similarity_score", "comparable_source_file"]])

    if not frames:
        return pd.DataFrame(columns=["target_id", "peer_id", "similarity_score", "comparable_source_file"]), profiles
    combined = pd.concat(frames, ignore_index=True)
    combined = combined[(combined["target_id"] != "") & (combined["peer_id"] != "")]
    combined = combined.dropna(subset=["similarity_score"])
    combined = combined.sort_values(["target_id", "similarity_score"], ascending=[True, False])
    combined = combined.drop_duplicates(["target_id", "peer_id"], keep="first")
    return combined, profiles


def annualized_peer_return(history: pd.DataFrame, peer_id: str) -> float | None:
    peer = history[history["canonical_tcgplayer_product_id"].astype(str) == peer_id].copy()
    if len(peer) < 2:
        return None
    peer["observation_date"] = pd.to_datetime(peer["observation_date"], errors="coerce")
    peer["market_price"] = pd.to_numeric(peer["market_price"], errors="coerce")
    peer = peer.dropna(subset=["observation_date", "market_price"]).sort_values("observation_date")
    peer = peer[peer["market_price"] > 0]
    if len(peer) < 2:
        return None
    first = peer.iloc[0]
    last = peer.iloc[-1]
    days = max((last["observation_date"] - first["observation_date"]).days, 1)
    ratio = float(last["market_price"]) / float(first["market_price"])
    if ratio <= 0:
        return None
    return ratio ** (365.25 / days) - 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    cfg = load_json(CONFIG)
    numeric = load_json(ROOT / cfg["inputs"]["numeric_specification"])
    dual_root = ROOT / cfg["inputs"]["dual_track_root"]
    out_dir = ROOT / cfg["output_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = dual_root / "collector_prospective_decision_snapshot.csv"
    history_path = dual_root / "collector_retrospective_outcome_history.csv"
    universe_path = dual_root / "collector_authoritative_universe.csv"
    product_master_path = ROOT / cfg["inputs"]["product_master"]
    for label, path in [("snapshot", snapshot_path), ("history", history_path), ("universe", universe_path), ("product_master", product_master_path)]:
        if not path.exists():
            failures.append(f"missing_{label}:{path}")

    if failures:
        print(json.dumps({"status": "FAIL", "failure_count": len(failures), "failures": failures}, indent=2))
        return 1 if args.strict else 0

    snapshot = pd.read_csv(snapshot_path, low_memory=False)
    history = pd.read_csv(history_path, low_memory=False)
    universe = pd.read_csv(universe_path, low_memory=False)
    master = pd.read_csv(product_master_path, low_memory=False)
    for frame in [snapshot, history, universe]:
        frame["canonical_tcgplayer_product_id"] = frame["canonical_tcgplayer_product_id"].map(norm_id)
    master["canonical_tcgplayer_product_id"] = master.get("tcgplayer_product_id", pd.Series(dtype=object)).map(norm_id)

    comparables, comparable_profiles = discover_comparables(cfg["inputs"]["comparable_search_roots"])
    comparable_profiles_df = pd.DataFrame(comparable_profiles)
    comparable_profiles_df.to_csv(out_dir / "collector_comparable_source_discovery.csv", index=False)
    comparables.to_csv(out_dir / "collector_discovered_comparable_edges.csv", index=False)

    master_columns = [
        "canonical_tcgplayer_product_id", "supply_score", "demand_score", "liquidity_score", "reprint_risk",
        "history_confidence", "data_quality_score", "return_90d", "return_180d", "return_365d",
    ]
    master_keep = master[[c for c in master_columns if c in master.columns]].drop_duplicates("canonical_tcgplayer_product_id")
    working = snapshot.merge(master_keep, on="canonical_tcgplayer_product_id", how="left", suffixes=("", "_master"))
    working = working.merge(
        universe[["canonical_tcgplayer_product_id", "future_release", "current_investment_eligible"]],
        on="canonical_tcgplayer_product_id", how="left", suffixes=("", "_universe")
    )

    methods = numeric["methods"]
    factor_cfg = numeric["market_factor_adjustment"]
    scenario_cfg = numeric["scenario_construction"]
    confidence_cfg = numeric["confidence"]
    rows: list[dict[str, Any]] = []
    peer_rows: list[dict[str, Any]] = []

    for _, row in working.iterrows():
        pid = row["canonical_tcgplayer_product_id"]
        route = str(row.get("forecast_method_route", "")).strip()
        method_cfg = methods.get(route, {})
        current_price = num(row.get("current_price"))

        history_returns = []
        for days, weight in method_cfg.get("candidate_window_weights", {}).items():
            value = num(row.get(f"return_{days}d"))
            if value is not None:
                history_returns.append((value, float(weight)))
        history_component = weighted_average(history_returns)

        target_edges = comparables[comparables["target_id"] == pid].copy()
        peer_values: list[tuple[float, float]] = []
        for _, edge in target_edges.iterrows():
            peer_return = annualized_peer_return(history, edge["peer_id"])
            score = float(edge["similarity_score"])
            if peer_return is not None and score > 0:
                peer_values.append((peer_return, score))
                peer_rows.append({
                    "target_tcgplayer_product_id": pid,
                    "peer_tcgplayer_product_id": edge["peer_id"],
                    "similarity_score": score,
                    "peer_annualized_retrospective_return": peer_return,
                    "source_file": edge["comparable_source_file"],
                    "decision_input_status": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
                })
        comparable_component = weighted_average(peer_values)

        neutral = float(factor_cfg["neutral_score"])
        coefficients = factor_cfg["factor_coefficients_annual_rate_points_per_10_score_points"]
        factor_inputs = {
            "supply": num(row.get("supply_score")),
            "demand": num(row.get("demand_score")),
            "liquidity": num(row.get("liquidity_score")),
            "reprint_risk": num(row.get("reprint_risk")),
        }
        factor_contributions: dict[str, float | None] = {}
        for name, value in factor_inputs.items():
            factor_contributions[name] = None if value is None else ((value - neutral) / 10.0) * float(coefficients[name]) / 100.0
        factor_adjustment = sum(v for v in factor_contributions.values() if v is not None)
        lower = float(factor_cfg["candidate_total_adjustment_lower_bound_annual_rate_points"]) / 100.0
        upper = float(factor_cfg["candidate_total_adjustment_upper_bound_annual_rate_points"]) / 100.0
        bounded_factor_adjustment = min(max(factor_adjustment, lower), upper)

        weights = {
            "history": float(method_cfg.get("history_weight", 0.0)),
            "comparable": float(method_cfg.get("comparable_weight", 0.0)),
            "fundamental": float(method_cfg.get("fundamental_weight", 0.0)),
        }
        components: list[tuple[float, float]] = []
        missing: list[str] = []
        if weights["history"] > 0:
            if history_component is None:
                missing.append("HISTORY_COMPONENT")
            else:
                components.append((history_component, weights["history"]))
        if weights["comparable"] > 0:
            if comparable_component is None:
                missing.append("COMPARABLE_COMPONENT")
            else:
                components.append((comparable_component, weights["comparable"]))
        if weights["fundamental"] > 0:
            components.append((bounded_factor_adjustment, weights["fundamental"]))

        core_rate = weighted_average(components)
        base_rate = None if core_rate is None else core_rate + (0.0 if weights["fundamental"] > 0 else bounded_factor_adjustment)

        dispersion_values = [v for v, _ in history_returns] + [v for v, _ in peer_values]
        dispersion = float(np.std(dispersion_values, ddof=0)) if len(dispersion_values) >= 2 else None
        evidence_penalty = 0.05 * len(missing)
        uncertainty_width = None if base_rate is None else max(dispersion or 0.0, evidence_penalty, 0.05)
        downside_rate = None if base_rate is None else base_rate - uncertainty_width
        upside_rate = None if base_rate is None else base_rate + uncertainty_width

        completeness = max(0.0, 100.0 - 25.0 * len(missing))
        agreement = 50.0 if dispersion is None else max(0.0, 100.0 - min(dispersion, 1.0) * 100.0)
        quality = num(row.get("history_confidence")) or num(row.get("data_quality_score")) or 0.0
        method_support = 100.0 if not missing else max(0.0, 100.0 - 40.0 * len(missing))
        confidence_weights = confidence_cfg["candidate_components"]
        confidence_score = (
            completeness * float(confidence_weights["evidence_completeness"]) +
            agreement * float(confidence_weights["evidence_agreement"]) +
            quality * float(confidence_weights["history_or_peer_quality"]) +
            method_support * float(confidence_weights["method_specific_support"])
        )
        confidence_class = "LOW"
        if confidence_score >= float(confidence_cfg["candidate_classes"]["HIGH"]["minimum_score"]):
            confidence_class = "HIGH"
        elif confidence_score >= float(confidence_cfg["candidate_classes"]["MODERATE"]["minimum_score"]):
            confidence_class = "MODERATE"

        output: dict[str, Any] = {
            "decision_date": row.get("decision_date"),
            "canonical_tcgplayer_product_id": pid,
            "product_name": row.get("product_name"),
            "release_date": row.get("release_date"),
            "future_release": row.get("future_release"),
            "current_investment_eligible": row.get("current_investment_eligible"),
            "current_price": current_price,
            "forecast_method_route": route,
            "candidate_model_version": row.get("candidate_model_version"),
            "history_component_annual_rate": history_component,
            "comparable_component_annual_rate": comparable_component,
            "fundamental_adjustment_annual_rate": bounded_factor_adjustment,
            "core_annual_rate": core_rate,
            "base_annual_rate": base_rate,
            "downside_annual_rate": downside_rate,
            "upside_annual_rate": upside_rate,
            "uncertainty_width": uncertainty_width,
            "confidence_score": confidence_score,
            "confidence_class": confidence_class,
            "selected_peer_count": len(peer_values),
            "missing_components": "|".join(missing),
            "candidate_calculation_complete": base_rate is not None and current_price is not None and not missing,
            "retrospective_inputs_used_for_diagnostics_only": True,
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        for horizon in scenario_cfg["horizons_years"]:
            for label, rate in [("downside", downside_rate), ("base", base_rate), ("upside", upside_rate)]:
                output[f"{label}_price_{horizon}y"] = None if current_price is None or rate is None or rate <= -1 else current_price * ((1.0 + rate) ** int(horizon))
        rows.append(output)

    forecasts = pd.DataFrame(rows)
    peer_df = pd.DataFrame(peer_rows)
    forecasts.to_csv(out_dir / "collector_candidate_forecast_diagnostics.csv", index=False)
    peer_df.to_csv(out_dir / "collector_candidate_peer_contributions.csv", index=False)

    route_summary = forecasts.groupby("forecast_method_route", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        complete_count=("candidate_calculation_complete", "sum"),
        mean_base_annual_rate=("base_annual_rate", "mean"),
        mean_confidence_score=("confidence_score", "mean"),
        mean_selected_peer_count=("selected_peer_count", "mean"),
    ).reset_index()
    route_summary.to_csv(out_dir / "collector_candidate_forecast_route_summary.csv", index=False)

    summary = {
        "audit_name": "Collector Candidate Forecast Diagnostics",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "product_count": int(len(forecasts)),
        "current_investment_eligible_count": int(pd.Series(forecasts["current_investment_eligible"]).astype(str).str.lower().eq("true").sum()),
        "candidate_calculation_complete_count": int(forecasts["candidate_calculation_complete"].sum()),
        "candidate_calculation_incomplete_count": int((~forecasts["candidate_calculation_complete"]).sum()),
        "discovered_comparable_edge_count": int(len(comparables)),
        "used_peer_contribution_count": int(len(peer_df)),
        "route_count": int(forecasts["forecast_method_route"].nunique(dropna=True)),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "governing_note": "This batch calculates inactive, fully disclosed diagnostics only. Retrospective history and peer returns are not represented as historically available decision inputs.",
    }
    (out_dir / "collector_candidate_forecast_diagnostics_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
