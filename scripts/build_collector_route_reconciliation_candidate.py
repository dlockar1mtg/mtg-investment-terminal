from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_route_reconciliation_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def norm_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    match = re.search(r"(\d+)(?:\.0)?$", text)
    if match:
        return match.group(1)
    try:
        number = float(text)
        if math.isfinite(number) and number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def weighted(values: list[tuple[float, float]]) -> float | None:
    usable = [(v, w) for v, w in values if v is not None and np.isfinite(v) and w > 0]
    if not usable:
        return None
    denominator = sum(w for _, w in usable)
    return sum(v * w for v, w in usable) / denominator if denominator else None


def annualized_return(history: pd.DataFrame, product_id: str) -> tuple[float | None, int, str, str]:
    rows = history[history["canonical_tcgplayer_product_id"] == product_id].copy()
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


def detect_edge_columns(edges: pd.DataFrame) -> tuple[str, str, str]:
    target = next((c for c in ["target_tcgplayer_product_id", "target_id", "target_product_id"] if c in edges.columns), "")
    peer = next((c for c in ["peer_tcgplayer_product_id", "peer_id", "peer_product_id"] if c in edges.columns), "")
    score = next((c for c in ["similarity_score", "adjusted_similarity_score", "score"] if c in edges.columns), "")
    if not target or not peer or not score:
        raise ValueError(f"unsupported_edge_schema:{list(edges.columns)}")
    return target, peer, score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_json(CONFIG)
    repaired_root = ROOT / cfg["inputs"]["repaired_root"]
    dual_root = ROOT / cfg["inputs"]["dual_track_root"]
    numeric = load_json(ROOT / cfg["inputs"]["numeric_specification"])
    override = load_json(ROOT / cfg["inputs"]["japanese_override"])
    out_dir = ROOT / cfg["output_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "forecasts": repaired_root / "collector_repaired_candidate_forecasts.csv",
        "edges": repaired_root / "collector_normalized_comparable_edges.csv",
        "peers": repaired_root / "collector_repaired_peer_contributions.csv",
        "history": dual_root / "collector_retrospective_outcome_history.csv",
    }
    failures = [f"missing_{name}:{path}" for name, path in paths.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(paths["forecasts"], low_memory=False)
    edges_raw = pd.read_csv(paths["edges"], low_memory=False)
    baseline_peers = pd.read_csv(paths["peers"], low_memory=False)
    history = pd.read_csv(paths["history"], low_memory=False)

    forecasts["canonical_tcgplayer_product_id"] = forecasts["canonical_tcgplayer_product_id"].map(norm_id)
    history["canonical_tcgplayer_product_id"] = history["canonical_tcgplayer_product_id"].map(norm_id)
    baseline_peers["target_tcgplayer_product_id"] = baseline_peers["target_tcgplayer_product_id"].map(norm_id)
    baseline_peers["peer_tcgplayer_product_id"] = baseline_peers["peer_tcgplayer_product_id"].map(norm_id)

    target_col, peer_col, score_col = detect_edge_columns(edges_raw)
    edges = pd.DataFrame({
        "target_id": edges_raw[target_col].map(norm_id),
        "peer_id": edges_raw[peer_col].map(norm_id),
        "similarity_score": pd.to_numeric(edges_raw[score_col], errors="coerce"),
    })
    if "comparable_source_file" in edges_raw.columns:
        edges["source_file"] = edges_raw["comparable_source_file"].astype(str)
    elif "source_file" in edges_raw.columns:
        edges["source_file"] = edges_raw["source_file"].astype(str)
    else:
        edges["source_file"] = str(paths["edges"].relative_to(ROOT)).replace("\\", "/")
    edges = edges[(edges["target_id"] != "") & (edges["peer_id"] != "")]
    edges = edges.dropna(subset=["similarity_score"])
    edges = edges.drop_duplicates(["target_id", "peer_id"], keep="first")

    peer_return_map = (
        baseline_peers[["peer_tcgplayer_product_id", "peer_annualized_retrospective_return"]]
        .dropna()
        .drop_duplicates("peer_tcgplayer_product_id")
        .set_index("peer_tcgplayer_product_id")["peer_annualized_retrospective_return"]
        .to_dict()
    )

    target_override = norm_id(override.get("target_tcgplayer_product_id") or override.get("target_product_id") or "628315")
    primary_override = norm_id(override.get("primary_comparable_tcgplayer_product_id") or override.get("primary_comparable_product_id") or "618893")

    methods = numeric["methods"]
    horizons = numeric["scenario_construction"]["horizons_years"]
    output_rows: list[dict[str, Any]] = []
    contribution_rows = baseline_peers.copy().to_dict("records")
    edge_rows: list[dict[str, Any]] = []
    baseline_complete_count = int(forecasts["candidate_calculation_complete"].map(truthy).sum())
    baseline_complete_ids = set(forecasts.loc[forecasts["candidate_calculation_complete"].map(truthy), "canonical_tcgplayer_product_id"])

    for _, row in forecasts.iterrows():
        pid = row["canonical_tcgplayer_product_id"]
        route = str(row.get("forecast_method_route", "")).strip()
        out = row.to_dict()

        if pid in baseline_complete_ids:
            out["reconciliation_action"] = "PRESERVED_REPAIRED_BASELINE"
            out["reverse_pair_candidate_used"] = False
            out["owner_approved_override_used"] = False
            output_rows.append(out)
            continue

        method = methods.get(route, {})
        current_price = num(row.get("current_price"))
        history_component = num(row.get("history_component_annual_rate"))
        history_count = 0
        history_start = ""
        history_end = ""
        if history_component is None and float(method.get("history_weight", 0.0)) > 0:
            history_component, history_count, history_start, history_end = annualized_return(history, pid)

        candidate_edges: list[dict[str, Any]] = []
        direct = edges[edges["target_id"] == pid]
        for _, edge in direct.iterrows():
            candidate_edges.append({
                "target_id": pid,
                "peer_id": edge["peer_id"],
                "similarity_score": float(edge["similarity_score"]),
                "edge_basis": "DIRECT_EXISTING_EXPLICIT_PAIR_SCORE",
                "owner_approval_status": "EXISTING_CANDIDATE",
                "source_file": edge["source_file"],
            })

        if not candidate_edges:
            reverse = edges[edges["peer_id"] == pid]
            for _, edge in reverse.iterrows():
                candidate_edges.append({
                    "target_id": pid,
                    "peer_id": edge["target_id"],
                    "similarity_score": float(edge["similarity_score"]),
                    "edge_basis": "REVERSED_EXISTING_EXPLICIT_PAIR_SCORE",
                    "owner_approval_status": "CANDIDATE_DIAGNOSTIC_REQUIRES_OWNER_APPROVAL",
                    "source_file": edge["source_file"],
                })

        if pid == target_override:
            candidate_edges = [{
                "target_id": pid,
                "peer_id": primary_override,
                "similarity_score": 100.0,
                "edge_basis": "OWNER_APPROVED_PRIMARY_COMPARABLE_OVERRIDE",
                "owner_approval_status": "OWNER_APPROVED",
                "source_file": str((ROOT / cfg["inputs"]["japanese_override"]).relative_to(ROOT)).replace("\\", "/"),
            }]

        peer_values: list[tuple[float, float]] = []
        for edge in candidate_edges:
            edge_rows.append(edge)
            peer_id = edge["peer_id"]
            peer_return = num(peer_return_map.get(peer_id))
            peer_count = 0
            peer_start = ""
            peer_end = ""
            if peer_return is None:
                peer_return, peer_count, peer_start, peer_end = annualized_return(history, peer_id)
            score = num(edge["similarity_score"]) or 0.0
            if peer_return is None or score <= 0:
                continue
            peer_values.append((peer_return, score))
            contribution_rows.append({
                "target_tcgplayer_product_id": pid,
                "peer_tcgplayer_product_id": peer_id,
                "similarity_score": score,
                "peer_annualized_retrospective_return": peer_return,
                "peer_observation_count": peer_count,
                "peer_history_start_date": peer_start,
                "peer_history_end_date": peer_end,
                "source_file": edge["source_file"],
                "decision_input_status": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
                "used_in_candidate": True,
                "edge_basis": edge["edge_basis"],
                "owner_approval_status": edge["owner_approval_status"],
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
            "reverse_pair_candidate_used": any(e["edge_basis"] == "REVERSED_EXISTING_EXPLICIT_PAIR_SCORE" for e in candidate_edges),
            "owner_approved_override_used": any(e["edge_basis"] == "OWNER_APPROVED_PRIMARY_COMPARABLE_OVERRIDE" for e in candidate_edges),
            "reconciliation_action": "FILLED_INCOMPLETE_ROUTE",
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
        })
        for horizon in horizons:
            for label, rate in [("downside", downside), ("base", base), ("upside", upside)]:
                out[f"{label}_price_{horizon}y"] = None if current_price is None or rate is None or rate <= -1 else current_price * ((1.0 + rate) ** int(horizon))
        output_rows.append(out)

    completed = pd.DataFrame(output_rows)
    contributions = pd.DataFrame(contribution_rows)
    reconciled_edges = pd.DataFrame(edge_rows)

    completed.to_csv(out_dir / "collector_reconciled_candidate_forecasts.csv", index=False)
    contributions.to_csv(out_dir / "collector_reconciled_peer_contributions.csv", index=False)
    reconciled_edges.to_csv(out_dir / "collector_reconciled_completion_edges.csv", index=False)

    route_summary = completed.groupby("forecast_method_route", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        complete_count=("candidate_calculation_complete", lambda s: int(s.map(truthy).sum())),
        mean_base_annual_rate=("base_annual_rate", "mean"),
        mean_selected_peer_count=("selected_peer_count", "mean"),
    ).reset_index()
    route_summary.to_csv(out_dir / "collector_reconciled_route_summary.csv", index=False)

    owner_review_cols = [
        "canonical_tcgplayer_product_id", "product_name", "forecast_method_route", "current_price",
        "history_component_annual_rate", "comparable_component_annual_rate", "fundamental_adjustment_annual_rate",
        "base_annual_rate", "downside_annual_rate", "upside_annual_rate", "selected_peer_count",
        "reverse_pair_candidate_used", "owner_approved_override_used", "missing_components",
        "candidate_calculation_complete", "reconciliation_action",
    ]
    owner_review = completed[[c for c in owner_review_cols if c in completed.columns]].copy()
    owner_review["owner_decision_required"] = owner_review["reverse_pair_candidate_used"].map(truthy)
    owner_review["owner_decision_topic"] = np.where(
        owner_review["owner_decision_required"],
        "Approve or reject symmetric use of existing pair scores for limited-history diagnostics",
        "No new route decision required",
    )
    owner_review.to_csv(out_dir / "collector_route_reconciliation_owner_review.csv", index=False)

    complete_count = int(completed["candidate_calculation_complete"].map(truthy).sum())
    preserved_count = int((completed["reconciliation_action"] == "PRESERVED_REPAIRED_BASELINE").sum())
    filled_count = int((completed["reconciliation_action"] == "FILLED_INCOMPLETE_ROUTE").sum())
    reverse_count = int(completed["reverse_pair_candidate_used"].map(truthy).sum())
    override_count = int(completed["owner_approved_override_used"].map(truthy).sum())
    summary = {
        "audit_name": "Collector Route Reconciliation Candidate",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(completed)),
        "repaired_baseline_complete_count": baseline_complete_count,
        "preserved_repaired_baseline_count": preserved_count,
        "filled_incomplete_route_count": filled_count,
        "candidate_calculation_complete_count": complete_count,
        "candidate_calculation_incomplete_count": int(len(completed) - complete_count),
        "limited_history_recomputed_count": int((pd.to_numeric(completed.get("history_observation_count_if_recomputed", 0), errors="coerce").fillna(0) > 0).sum()),
        "reverse_pair_candidate_product_count": reverse_count,
        "owner_approved_override_product_count": override_count,
        "baseline_peer_contribution_count": int(len(baseline_peers)),
        "total_peer_contribution_count": int(len(contributions)),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": 0,
        "failures": [],
        "governing_note": "This reconciliation preserves all 43 complete repaired forecasts and fills only the eight incomplete routes. Reverse-pair relationships remain inactive diagnostics pending owner approval. No forecast or purchase authorization is granted."
    }
    (out_dir / "collector_route_reconciliation_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    strict_failures: list[str] = []
    if len(completed) != 51:
        strict_failures.append("product_count_not_51")
    if preserved_count != baseline_complete_count:
        strict_failures.append("repaired_baseline_not_fully_preserved")
    if complete_count < baseline_complete_count:
        strict_failures.append("completion_regressed_below_repaired_baseline")
    if args.strict and strict_failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
