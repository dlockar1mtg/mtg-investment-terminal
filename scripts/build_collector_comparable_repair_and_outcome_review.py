from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_comparable_repair_and_outcome_review_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    match = re.search(r"(\d+)(?:\.0+)?$", text)
    return match.group(1) if match else text


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) or not np.isfinite(parsed) else float(parsed)


def weighted_average(values: list[tuple[float, float]]) -> float | None:
    usable = [(v, w) for v, w in values if v is not None and np.isfinite(v) and w > 0]
    if not usable:
        return None
    total = sum(w for _, w in usable)
    return sum(v * w for v, w in usable) / total if total else None


def annualized_return(history: pd.DataFrame, pid: str) -> tuple[float | None, int, str, str]:
    peer = history[history["canonical_tcgplayer_product_id"] == pid].copy()
    peer["observation_date"] = pd.to_datetime(peer["observation_date"], errors="coerce")
    peer["market_price"] = pd.to_numeric(peer["market_price"], errors="coerce")
    peer = peer.dropna(subset=["observation_date", "market_price"])
    peer = peer[peer["market_price"] > 0].sort_values("observation_date")
    if len(peer) < 2:
        return None, len(peer), "", ""
    first, last = peer.iloc[0], peer.iloc[-1]
    days = max((last["observation_date"] - first["observation_date"]).days, 1)
    ratio = float(last["market_price"]) / float(first["market_price"])
    if ratio <= 0:
        return None, len(peer), "", ""
    return ratio ** (365.25 / days) - 1.0, len(peer), first["observation_date"].date().isoformat(), last["observation_date"].date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    cfg = load_json(CONFIG)
    forecast_root = ROOT / cfg["inputs"]["forecast_root"]
    dual_root = ROOT / cfg["inputs"]["dual_track_root"]
    numeric = load_json(ROOT / cfg["inputs"]["numeric_specification"])
    out = ROOT / cfg["output_directory"]
    out.mkdir(parents=True, exist_ok=True)

    paths = {
        "forecast": forecast_root / "collector_candidate_forecast_diagnostics.csv",
        "edges": forecast_root / "collector_discovered_comparable_edges.csv",
        "history": dual_root / "collector_retrospective_outcome_history.csv",
        "snapshot": dual_root / "collector_prospective_decision_snapshot.csv",
    }
    for label, path in paths.items():
        if not path.exists():
            failures.append(f"missing_{label}:{path}")
    if failures:
        print(json.dumps({"status": "FAIL", "failure_count": len(failures), "failures": failures}, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(paths["forecast"], low_memory=False)
    edges = pd.read_csv(paths["edges"], low_memory=False)
    history = pd.read_csv(paths["history"], low_memory=False)
    snapshot = pd.read_csv(paths["snapshot"], low_memory=False)
    for frame in [forecasts, history, snapshot]:
        frame["canonical_tcgplayer_product_id"] = frame["canonical_tcgplayer_product_id"].map(norm_id)
    edges["target_numeric_id"] = edges["target_id"].map(norm_id)
    edges["peer_numeric_id"] = edges["peer_id"].map(norm_id)
    edges["similarity_score"] = pd.to_numeric(edges["similarity_score"], errors="coerce")
    edges["source_priority"] = edges.get("comparable_source_file", "").astype(str).str.contains("selected_comparables").map({True: 0, False: 1})
    edges = edges.dropna(subset=["similarity_score"])
    edges = edges[(edges["target_numeric_id"] != "") & (edges["peer_numeric_id"] != "")]
    edges = edges.sort_values(["target_numeric_id", "peer_numeric_id", "source_priority", "similarity_score"], ascending=[True, True, True, False])
    edges = edges.drop_duplicates(["target_numeric_id", "peer_numeric_id"], keep="first")

    peer_cache: dict[str, tuple[float | None, int, str, str]] = {}
    peer_rows: list[dict] = []
    repaired_rows: list[dict] = []
    numeric_methods = numeric["methods"]
    horizons = numeric["scenario_construction"]["horizons_years"]
    validated = {str(x["tcgplayer_product_id"]): x["validation_status"] for x in cfg["owner_validated_prices"]}

    for _, row in forecasts.iterrows():
        pid = norm_id(row["canonical_tcgplayer_product_id"])
        route = str(row.get("forecast_method_route", ""))
        method = numeric_methods.get(route, {})
        target_edges = edges[edges["target_numeric_id"] == pid].copy()
        peer_values: list[tuple[float, float]] = []
        for _, edge in target_edges.iterrows():
            peer_id = edge["peer_numeric_id"]
            if peer_id not in peer_cache:
                peer_cache[peer_id] = annualized_return(history, peer_id)
            peer_return, obs_count, start_date, end_date = peer_cache[peer_id]
            usable = peer_return is not None and float(edge["similarity_score"]) > 0
            peer_rows.append({
                "target_tcgplayer_product_id": pid,
                "peer_tcgplayer_product_id": peer_id,
                "target_canonical_id": edge["target_id"],
                "peer_canonical_id": edge["peer_id"],
                "similarity_score": edge["similarity_score"],
                "peer_annualized_retrospective_return": peer_return,
                "peer_observation_count": obs_count,
                "peer_history_start_date": start_date,
                "peer_history_end_date": end_date,
                "source_file": edge.get("comparable_source_file", ""),
                "used_in_candidate": usable,
                "decision_input_status": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
            })
            if usable:
                peer_values.append((float(peer_return), float(edge["similarity_score"])))

        comparable = weighted_average(peer_values)
        history_component = num(row.get("history_component_annual_rate"))
        fundamental = num(row.get("fundamental_adjustment_annual_rate")) or 0.0
        hw = float(method.get("history_weight", 0.0))
        cw = float(method.get("comparable_weight", 0.0))
        fw = float(method.get("fundamental_weight", 0.0))
        missing: list[str] = []
        components: list[tuple[float, float]] = []
        if hw > 0:
            if history_component is None:
                missing.append("HISTORY_COMPONENT")
            else:
                components.append((history_component, hw))
        if cw > 0:
            if comparable is None:
                missing.append("COMPARABLE_COMPONENT")
            else:
                components.append((comparable, cw))
        if fw > 0:
            components.append((fundamental, fw))
        core = weighted_average(components)
        base = None if core is None else core + (0.0 if fw > 0 else fundamental)
        dispersion_values = [v for v, _ in peer_values]
        if history_component is not None:
            dispersion_values.append(history_component)
        dispersion = float(np.std(dispersion_values, ddof=0)) if len(dispersion_values) >= 2 else 0.05
        uncertainty = None if base is None else max(dispersion, 0.05 * len(missing), 0.05)
        downside = None if base is None else base - uncertainty
        upside = None if base is None else base + uncertainty
        current_price = num(row.get("current_price"))
        output = row.to_dict()
        output.update({
            "comparable_component_annual_rate": comparable,
            "core_annual_rate": core,
            "base_annual_rate": base,
            "downside_annual_rate": downside,
            "upside_annual_rate": upside,
            "uncertainty_width": uncertainty,
            "selected_peer_count": len(peer_values),
            "missing_components": "|".join(missing),
            "candidate_calculation_complete": bool(base is not None and current_price is not None and not missing),
            "owner_price_validation_status": validated.get(pid, "NOT_SPECIFICALLY_OWNER_VALIDATED"),
            "retrospective_inputs_used_for_diagnostics_only": True,
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
        })
        for horizon in horizons:
            for label, rate in [("downside", downside), ("base", base), ("upside", upside)]:
                output[f"{label}_price_{horizon}y"] = None if current_price is None or rate is None or rate <= -1 else current_price * ((1 + rate) ** int(horizon))
        repaired_rows.append(output)

    repaired = pd.DataFrame(repaired_rows)
    peers = pd.DataFrame(peer_rows)
    repaired.to_csv(out / "collector_repaired_candidate_forecasts.csv", index=False)
    peers.to_csv(out / "collector_repaired_peer_contributions.csv", index=False)
    edges.to_csv(out / "collector_normalized_comparable_edges.csv", index=False)

    current = repaired[pd.to_numeric(repaired["current_investment_eligible"], errors="coerce").fillna(0).astype(bool)].copy()
    complete = repaired[repaired["candidate_calculation_complete"] == True].copy()  # noqa: E712
    route_summary = repaired.groupby("forecast_method_route", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        complete_count=("candidate_calculation_complete", "sum"),
        mean_base_annual_rate=("base_annual_rate", "mean"),
        mean_selected_peer_count=("selected_peer_count", "mean"),
    ).reset_index()
    route_summary.to_csv(out / "collector_repaired_route_summary.csv", index=False)

    review = repaired[[
        "canonical_tcgplayer_product_id", "product_name", "forecast_method_route", "current_price",
        "history_component_annual_rate", "comparable_component_annual_rate", "fundamental_adjustment_annual_rate",
        "base_annual_rate", "downside_annual_rate", "upside_annual_rate", "selected_peer_count",
        "missing_components", "candidate_calculation_complete", "owner_price_validation_status"
    ]].copy()
    review.to_csv(out / "collector_owner_methodology_review.csv", index=False)

    summary = {
        "audit_name": "Collector Comparable Repair and Outcome Review",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "product_count": int(len(repaired)),
        "current_investment_eligible_count": int(len(current)),
        "normalized_comparable_edge_count": int(len(edges)),
        "peer_contribution_row_count": int(len(peers)),
        "used_peer_contribution_count": int(peers["used_in_candidate"].fillna(False).sum()) if not peers.empty else 0,
        "candidate_calculation_complete_count": int(repaired["candidate_calculation_complete"].fillna(False).sum()),
        "candidate_calculation_incomplete_count": int((~repaired["candidate_calculation_complete"].fillna(False)).sum()),
        "owner_validated_price_count": int((repaired["owner_price_validation_status"] == "OWNER_VALIDATED_CURRENT_PRICE").sum()),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "governing_note": "Comparable IDs are normalized and peer contributions are retrospective diagnostics only. No forecast or purchase authorization is granted."
    }
    (out / "collector_comparable_repair_and_outcome_review_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
