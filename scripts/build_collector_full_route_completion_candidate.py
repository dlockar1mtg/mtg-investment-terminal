from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_full_route_completion_candidate_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def annualized_return(history: pd.DataFrame, product_id: str) -> tuple[float | None, int, str, str]:
    rows = history[history["canonical_tcgplayer_product_id"].astype(str) == str(product_id)].copy()
    rows["observation_date"] = pd.to_datetime(rows["observation_date"], errors="coerce")
    rows["market_price"] = pd.to_numeric(rows["market_price"], errors="coerce")
    rows = rows.dropna(subset=["observation_date", "market_price"])
    rows = rows[rows["market_price"] > 0].sort_values("observation_date")
    if len(rows) < 2:
        return None, len(rows), "", ""
    first, last = rows.iloc[0], rows.iloc[-1]
    days = max((last["observation_date"] - first["observation_date"]).days, 1)
    ratio = float(last["market_price"]) / float(first["market_price"])
    if ratio <= 0:
        return None, len(rows), str(first["observation_date"].date()), str(last["observation_date"].date())
    return ratio ** (365.25 / days) - 1.0, len(rows), str(first["observation_date"].date()), str(last["observation_date"].date())


def weighted(values: list[tuple[float, float]]) -> float | None:
    usable = [(v, w) for v, w in values if v is not None and np.isfinite(v) and w > 0]
    if not usable:
        return None
    denominator = sum(w for _, w in usable)
    return sum(v * w for v, w in usable) / denominator if denominator else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_json(CONFIG)
    repair_root = ROOT / cfg["inputs"]["repair_root"]
    dual_root = ROOT / cfg["inputs"]["dual_track_root"]
    numeric = load_json(ROOT / cfg["inputs"]["numeric_specification"])
    override = load_json(ROOT / cfg["inputs"]["japanese_override"])
    out_dir = ROOT / cfg["output_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)

    required = {
        "forecasts": repair_root / "collector_repaired_candidate_forecasts.csv",
        "edges": repair_root / "collector_normalized_comparable_edges.csv",
        "peers": repair_root / "collector_repaired_peer_contributions.csv",
        "history": dual_root / "collector_retrospective_outcome_history.csv",
    }
    failures = [f"missing_{name}:{path}" for name, path in required.items() if not path.exists()]
    if failures:
        print(json.dumps({"status": "FAIL", "failure_count": len(failures), "failures": failures}, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(required["forecasts"], low_memory=False)
    edges = pd.read_csv(required["edges"], low_memory=False)
    peer_contrib = pd.read_csv(required["peers"], low_memory=False)
    history = pd.read_csv(required["history"], low_memory=False)

    for frame, cols in [
        (forecasts, ["canonical_tcgplayer_product_id"]),
        (edges, ["target_tcgplayer_product_id", "peer_tcgplayer_product_id"]),
        (peer_contrib, ["target_tcgplayer_product_id", "peer_tcgplayer_product_id"]),
        (history, ["canonical_tcgplayer_product_id"]),
    ]:
        for col in cols:
            if col in frame.columns:
                frame[col] = frame[col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

    peer_returns = (
        peer_contrib[["peer_tcgplayer_product_id", "peer_annualized_retrospective_return"]]
        .dropna()
        .drop_duplicates("peer_tcgplayer_product_id")
        .set_index("peer_tcgplayer_product_id")["peer_annualized_retrospective_return"]
        .to_dict()
    )

    direct_edge_targets = set(edges["target_tcgplayer_product_id"].astype(str))
    completion_edges: list[dict[str, Any]] = []
    for _, edge in edges.iterrows():
        completion_edges.append({
            "target_id": str(edge["target_tcgplayer_product_id"]),
            "peer_id": str(edge["peer_tcgplayer_product_id"]),
            "similarity_score": num(edge.get("similarity_score")) or 0.0,
            "edge_basis": "DIRECT_EXISTING_EXPLICIT_PAIR_SCORE",
            "owner_approval_status": "EXISTING_CANDIDATE",
        })

    incomplete_ids = set(
        forecasts.loc[forecasts["candidate_calculation_complete"].astype(str) != "True", "canonical_tcgplayer_product_id"].astype(str)
    )
    for target_id in sorted(incomplete_ids):
        if target_id in direct_edge_targets:
            continue
        reverse = edges[edges["peer_tcgplayer_product_id"].astype(str) == target_id]
        for _, edge in reverse.iterrows():
            completion_edges.append({
                "target_id": target_id,
                "peer_id": str(edge["target_tcgplayer_product_id"]),
                "similarity_score": num(edge.get("similarity_score")) or 0.0,
                "edge_basis": "REVERSED_EXISTING_EXPLICIT_PAIR_SCORE",
                "owner_approval_status": "CANDIDATE_DIAGNOSTIC_REQUIRES_OWNER_APPROVAL",
            })

    target_override = str(override.get("target_tcgplayer_product_id") or override.get("target_product_id") or "628315").split("-")[-1]
    primary_override = str(override.get("primary_comparable_tcgplayer_product_id") or override.get("primary_comparable_product_id") or "618893").split("-")[-1]
    completion_edges.append({
        "target_id": target_override,
        "peer_id": primary_override,
        "similarity_score": 100.0,
        "edge_basis": "OWNER_APPROVED_PRIMARY_COMPARABLE_OVERRIDE",
        "owner_approval_status": "OWNER_APPROVED",
    })

    completion_edges_df = pd.DataFrame(completion_edges).drop_duplicates(["target_id", "peer_id"], keep="last")
    completion_edges_df.to_csv(out_dir / "collector_full_route_comparable_edges.csv", index=False)

    methods = numeric["methods"]
    scenarios = numeric["scenario_construction"]["horizons_years"]
    output_rows: list[dict[str, Any]] = []
    contribution_rows: list[dict[str, Any]] = []

    for _, row in forecasts.iterrows():
        pid = str(row["canonical_tcgplayer_product_id"])
        route = str(row["forecast_method_route"])
        method = methods[route]
        current_price = num(row.get("current_price"))
        history_component = num(row.get("history_component_annual_rate"))
        history_count = 0
        history_start = ""
        history_end = ""
        if history_component is None and float(method.get("history_weight", 0.0)) > 0:
            history_component, history_count, history_start, history_end = annualized_return(history, pid)

        target_edges = completion_edges_df[completion_edges_df["target_id"] == pid].copy()
        peer_values: list[tuple[float, float]] = []
        for _, edge in target_edges.iterrows():
            peer_id = str(edge["peer_id"])
            peer_return = num(peer_returns.get(peer_id))
            if peer_return is None:
                peer_return, peer_count, peer_start, peer_end = annualized_return(history, peer_id)
            else:
                peer_count = 0
                peer_start = ""
                peer_end = ""
            score = num(edge["similarity_score"]) or 0.0
            if peer_return is None or score <= 0:
                continue
            peer_values.append((peer_return, score))
            contribution_rows.append({
                "target_tcgplayer_product_id": pid,
                "peer_tcgplayer_product_id": peer_id,
                "similarity_score": score,
                "peer_annualized_retrospective_return": peer_return,
                "edge_basis": edge["edge_basis"],
                "owner_approval_status": edge["owner_approval_status"],
                "decision_input_status": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
                "used_in_candidate": True,
                "peer_observation_count_if_recomputed": peer_count,
                "peer_history_start_if_recomputed": peer_start,
                "peer_history_end_if_recomputed": peer_end,
            })
        comparable_component = weighted(peer_values)

        history_weight = float(method.get("history_weight", 0.0))
        comparable_weight = float(method.get("comparable_weight", 0.0))
        fundamental_weight = float(method.get("fundamental_weight", 0.0))
        fundamental = num(row.get("fundamental_adjustment_annual_rate")) or 0.0
        components: list[tuple[float, float]] = []
        missing: list[str] = []
        if history_weight > 0:
            if history_component is None:
                missing.append("HISTORY_COMPONENT")
            else:
                components.append((history_component, history_weight))
        if comparable_weight > 0:
            if comparable_component is None:
                missing.append("COMPARABLE_COMPONENT")
            else:
                components.append((comparable_component, comparable_weight))
        if fundamental_weight > 0:
            components.append((fundamental, fundamental_weight))

        core = weighted(components)
        base = None if core is None else core + (0.0 if fundamental_weight > 0 else fundamental)
        dispersion_values = [v for v, _ in peer_values]
        if history_component is not None:
            dispersion_values.append(history_component)
        width = None if base is None else max(float(np.std(dispersion_values)) if len(dispersion_values) > 1 else 0.05, 0.05)
        downside = None if base is None else base - width
        upside = None if base is None else base + width

        out = row.to_dict()
        out.update({
            "history_component_annual_rate": history_component,
            "comparable_component_annual_rate": comparable_component,
            "core_annual_rate": core,
            "base_annual_rate": base,
            "downside_annual_rate": downside,
            "upside_annual_rate": upside,
            "uncertainty_width": width,
            "selected_peer_count": len(peer_values),
            "history_observation_count_if_recomputed": history_count,
            "history_start_if_recomputed": history_start,
            "history_end_if_recomputed": history_end,
            "missing_components": "|".join(missing),
            "candidate_calculation_complete": base is not None and current_price is not None and not missing,
            "reverse_pair_candidate_used": any(e == "REVERSED_EXISTING_EXPLICIT_PAIR_SCORE" for e in target_edges["edge_basis"]),
            "owner_approved_override_used": any(e == "OWNER_APPROVED_PRIMARY_COMPARABLE_OVERRIDE" for e in target_edges["edge_basis"]),
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
        })
        for horizon in scenarios:
            for label, rate in [("downside", downside), ("base", base), ("upside", upside)]:
                out[f"{label}_price_{horizon}y"] = None if current_price is None or rate is None or rate <= -1 else current_price * ((1 + rate) ** int(horizon))
        output_rows.append(out)

    completed = pd.DataFrame(output_rows)
    contributions = pd.DataFrame(contribution_rows)
    completed.to_csv(out_dir / "collector_full_route_candidate_forecasts.csv", index=False)
    contributions.to_csv(out_dir / "collector_full_route_peer_contributions.csv", index=False)

    route_summary = completed.groupby("forecast_method_route", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        complete_count=("candidate_calculation_complete", "sum"),
        mean_base_annual_rate=("base_annual_rate", "mean"),
        mean_selected_peer_count=("selected_peer_count", "mean"),
    ).reset_index()
    route_summary.to_csv(out_dir / "collector_full_route_summary_by_route.csv", index=False)

    owner_review = completed[[
        "canonical_tcgplayer_product_id", "product_name", "forecast_method_route", "current_price",
        "history_component_annual_rate", "comparable_component_annual_rate", "fundamental_adjustment_annual_rate",
        "base_annual_rate", "downside_annual_rate", "upside_annual_rate", "selected_peer_count",
        "reverse_pair_candidate_used", "owner_approved_override_used", "missing_components",
        "candidate_calculation_complete",
    ]].copy()
    owner_review["owner_decision_required"] = owner_review["reverse_pair_candidate_used"].astype(bool)
    owner_review["owner_decision_topic"] = np.where(
        owner_review["owner_decision_required"],
        "Approve or reject symmetric use of existing pair scores for limited-history diagnostics",
        "No new route decision required",
    )
    owner_review.to_csv(out_dir / "collector_full_route_owner_review.csv", index=False)

    complete_count = int(completed["candidate_calculation_complete"].astype(bool).sum())
    summary = {
        "audit_name": "Collector Full-Route Completion Candidate",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(completed)),
        "candidate_calculation_complete_count": complete_count,
        "candidate_calculation_incomplete_count": int(len(completed) - complete_count),
        "limited_history_recomputed_count": int((completed["history_observation_count_if_recomputed"] > 0).sum()),
        "reverse_pair_candidate_product_count": int(completed["reverse_pair_candidate_used"].astype(bool).sum()),
        "owner_approved_override_product_count": int(completed["owner_approved_override_used"].astype(bool).sum()),
        "peer_contribution_count": int(len(contributions)),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": 0,
        "failures": [],
        "governing_note": "This batch completes route diagnostics using existing numeric weights, governed retrospective history, candidate symmetric reuse of existing pair scores, and the owner-approved Japanese FINAL FANTASY primary comparable. Reverse-pair use remains subject to owner approval and no forecast or purchase authorization is granted."
    }
    (out_dir / "collector_full_route_completion_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
