from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_methodology_evidence_review_v1.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    reconciliation_root = ROOT / cfg["inputs"]["reconciliation_root"]
    dual_root = ROOT / cfg["inputs"]["dual_track_root"]
    out_dir = ROOT / cfg["output_directory"]
    ledger_dir = ROOT / cfg["prospective_ledger_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_dir.mkdir(parents=True, exist_ok=True)

    required = {
        "forecasts": reconciliation_root / "collector_reconciled_candidate_forecasts.csv",
        "peers": reconciliation_root / "collector_reconciled_peer_contributions.csv",
        "edges": reconciliation_root / "collector_reconciled_completion_edges.csv",
        "history": dual_root / "collector_retrospective_outcome_history.csv",
        "snapshot": dual_root / "collector_prospective_decision_snapshot.csv",
    }
    missing = [f"missing_{name}:{path}" for name, path in required.items() if not path.exists()]
    if missing:
        result = {"status": "FAIL", "failure_count": len(missing), "failures": missing}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(required["forecasts"], low_memory=False)
    peers = pd.read_csv(required["peers"], low_memory=False)
    history = pd.read_csv(required["history"], low_memory=False)
    snapshot = pd.read_csv(required["snapshot"], low_memory=False)

    failures: list[str] = []
    if len(forecasts) != 51:
        failures.append(f"forecast_product_count_expected_51_actual_{len(forecasts)}")
    if int(forecasts["candidate_calculation_complete"].map(truthy).sum()) != 51:
        failures.append("all_51_candidate_calculations_not_complete")

    peer_used = peers[peers.get("used_in_candidate", True).map(truthy)].copy() if "used_in_candidate" in peers.columns else peers.copy()
    peer_used["similarity_score"] = pd.to_numeric(peer_used.get("similarity_score"), errors="coerce")
    peer_used["peer_annualized_retrospective_return"] = pd.to_numeric(
        peer_used.get("peer_annualized_retrospective_return"), errors="coerce"
    )
    peer_used = peer_used.dropna(subset=["target_tcgplayer_product_id", "peer_tcgplayer_product_id", "similarity_score"])
    peer_used = peer_used[peer_used["similarity_score"] > 0]

    concentration_rows: list[dict[str, Any]] = []
    for target_id, group in peer_used.groupby("target_tcgplayer_product_id"):
        total = float(group["similarity_score"].sum())
        weights = group["similarity_score"] / total if total > 0 else pd.Series(dtype=float)
        concentration_rows.append({
            "target_tcgplayer_product_id": str(target_id),
            "peer_count": int(len(group)),
            "largest_peer_weight": float(weights.max()) if len(weights) else None,
            "top_3_peer_weight": float(weights.nlargest(3).sum()) if len(weights) else None,
            "effective_peer_count": float(1.0 / (weights.pow(2).sum())) if len(weights) and weights.pow(2).sum() > 0 else None,
            "mean_peer_return": float(group["peer_annualized_retrospective_return"].mean()),
            "median_peer_return": float(group["peer_annualized_retrospective_return"].median()),
            "peer_return_std": float(group["peer_annualized_retrospective_return"].std(ddof=0)),
            "reverse_pair_used": bool((group.get("edge_basis", "") == "REVERSED_EXISTING_EXPLICIT_PAIR_SCORE").any()) if "edge_basis" in group.columns else False,
        })
    concentration = pd.DataFrame(concentration_rows)

    forecasts["canonical_tcgplayer_product_id"] = forecasts["canonical_tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    concentration["target_tcgplayer_product_id"] = concentration.get("target_tcgplayer_product_id", pd.Series(dtype=str)).astype(str)
    review = forecasts.merge(
        concentration,
        how="left",
        left_on="canonical_tcgplayer_product_id",
        right_on="target_tcgplayer_product_id",
    )
    review["base_annual_rate"] = pd.to_numeric(review.get("base_annual_rate"), errors="coerce")
    review["downside_annual_rate"] = pd.to_numeric(review.get("downside_annual_rate"), errors="coerce")
    review["upside_annual_rate"] = pd.to_numeric(review.get("upside_annual_rate"), errors="coerce")
    review["history_observation_count_if_recomputed"] = pd.to_numeric(
        review.get("history_observation_count_if_recomputed"), errors="coerce"
    ).fillna(0)
    review["short_history_flag"] = (
        (review["forecast_method_route"] == "DIRECT_HISTORY_LIMITED")
        | (review["history_observation_count_if_recomputed"].between(1, 12))
    )
    review["extreme_base_rate_flag"] = review["base_annual_rate"].abs() >= 1.0
    review["negative_base_rate_flag"] = review["base_annual_rate"] < 0
    review["high_peer_concentration_flag"] = pd.to_numeric(review.get("largest_peer_weight"), errors="coerce") >= 0.25
    review["methodology_review_required"] = (
        review.get("reverse_pair_candidate_used", False).map(truthy)
        | review["short_history_flag"]
        | review["extreme_base_rate_flag"]
        | review["high_peer_concentration_flag"]
        | review.get("owner_approved_override_used", False).map(truthy)
    )

    history["observation_date"] = pd.to_datetime(history.get("observation_date"), errors="coerce")
    history["market_price"] = pd.to_numeric(history.get("market_price"), errors="coerce")
    history_valid = history.dropna(subset=["observation_date", "market_price"])
    history_valid = history_valid[history_valid["market_price"] > 0].copy()
    outcome_rows: list[dict[str, Any]] = []
    for pid, group in history_valid.groupby("canonical_tcgplayer_product_id"):
        group = group.sort_values("observation_date")
        prices = group["market_price"]
        running_max = prices.cummax()
        drawdowns = prices / running_max - 1.0
        outcome_rows.append({
            "canonical_tcgplayer_product_id": str(pid).replace(".0", ""),
            "observation_count": int(len(group)),
            "history_start": str(group["observation_date"].iloc[0].date()),
            "history_end": str(group["observation_date"].iloc[-1].date()),
            "start_price": float(prices.iloc[0]),
            "end_price": float(prices.iloc[-1]),
            "simple_return": float(prices.iloc[-1] / prices.iloc[0] - 1.0) if prices.iloc[0] > 0 else None,
            "maximum_drawdown": float(drawdowns.min()),
            "price_volatility": float(prices.pct_change().dropna().std(ddof=0)) if len(prices) > 1 else None,
            "decision_input_status": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
        })
    outcomes = pd.DataFrame(outcome_rows)

    route_summary = review.groupby("forecast_method_route", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        mean_base_annual_rate=("base_annual_rate", "mean"),
        median_base_annual_rate=("base_annual_rate", "median"),
        negative_base_rate_count=("negative_base_rate_flag", "sum"),
        extreme_base_rate_count=("extreme_base_rate_flag", "sum"),
        short_history_count=("short_history_flag", "sum"),
        high_peer_concentration_count=("high_peer_concentration_flag", "sum"),
        methodology_review_required_count=("methodology_review_required", "sum"),
    ).reset_index()

    decision_rows = []
    for topic, required_count, status, scope in [
        ("Symmetric reuse of existing comparable scores for seven limited-history products", int(review.get("reverse_pair_candidate_used", False).map(truthy).sum()), "PENDING_OWNER_DECISION", "ROUTE_EVIDENCE_ONLY"),
        ("Annualization treatment for short histories", int(review["short_history_flag"].sum()), "PENDING_OWNER_DECISION", "NUMERIC_METHODOLOGY"),
        ("Treatment of absolute base annual rates at or above 100%", int(review["extreme_base_rate_flag"].sum()), "PENDING_OWNER_DECISION", "NUMERIC_METHODOLOGY"),
        ("Peer concentration threshold and minimum effective peer count", int(review["high_peer_concentration_flag"].sum()), "PENDING_OWNER_DECISION", "COMPARABLE_METHODOLOGY"),
        ("Japanese FINAL FANTASY primary comparable override", int(review.get("owner_approved_override_used", False).map(truthy).sum()), "OWNER_APPROVED_COMPARABLE_ONLY", "ROUTE_EVIDENCE_ONLY"),
    ]:
        decision_rows.append({
            "decision_topic": topic,
            "affected_product_count": required_count,
            "current_status": status,
            "approval_scope": scope,
            "forecast_authorization_granted": False,
            "purchase_authorization_granted": False,
        })
    decisions = pd.DataFrame(decision_rows)

    capture_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot_key_cols = [c for c in ["decision_date", "canonical_tcgplayer_product_id", "candidate_model_version"] if c in snapshot.columns]
    snapshot_copy = snapshot.copy()
    snapshot_copy["captured_to_ledger_at_utc"] = capture_time
    snapshot_copy["source_snapshot_sha256"] = file_sha256(required["snapshot"])
    ledger_path = ledger_dir / "collector_prospective_decision_snapshot_ledger.csv"
    if ledger_path.exists():
        existing = pd.read_csv(ledger_path, low_memory=False)
        combined = pd.concat([existing, snapshot_copy], ignore_index=True, sort=False)
    else:
        combined = snapshot_copy
    if snapshot_key_cols:
        combined = combined.drop_duplicates(snapshot_key_cols, keep="first")
    combined.to_csv(ledger_path, index=False)

    concentration.to_csv(out_dir / "collector_peer_concentration_diagnostics.csv", index=False)
    outcomes.to_csv(out_dir / "collector_retrospective_outcome_diagnostics.csv", index=False)
    route_summary.to_csv(out_dir / "collector_route_risk_summary.csv", index=False)
    review.to_csv(out_dir / "collector_methodology_product_review.csv", index=False)
    decisions.to_csv(out_dir / "collector_owner_methodology_decisions.csv", index=False)

    summary = {
        "audit_name": "Collector Methodology Evidence Review",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(forecasts)),
        "complete_candidate_count": int(forecasts["candidate_calculation_complete"].map(truthy).sum()),
        "peer_contribution_count": int(len(peer_used)),
        "reverse_pair_product_count": int(review.get("reverse_pair_candidate_used", False).map(truthy).sum()),
        "short_history_product_count": int(review["short_history_flag"].sum()),
        "extreme_base_rate_product_count": int(review["extreme_base_rate_flag"].sum()),
        "negative_base_rate_product_count": int(review["negative_base_rate_flag"].sum()),
        "high_peer_concentration_product_count": int(review["high_peer_concentration_flag"].sum()),
        "methodology_review_required_product_count": int(review["methodology_review_required"].sum()),
        "retrospective_outcome_product_count": int(len(outcomes)),
        "prospective_ledger_row_count": int(len(combined)),
        "prospective_snapshot_sha256": file_sha256(required["snapshot"]),
        "future_information_prohibited": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This batch evaluates route risk, peer concentration, short-history stability, retrospective outcomes, and prospective evidence capture. It does not validate forecast accuracy, approve symmetric comparable reuse, activate parameters, authorize forecasts, or authorize purchases."
    }
    (out_dir / "collector_methodology_evidence_review_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
