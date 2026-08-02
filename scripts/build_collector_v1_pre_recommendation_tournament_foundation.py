from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WINNER_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_short_horizon_winners"
EXPANDED_DIR = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament"
COHORT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_cohort_fallback_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_pre_recommendation_tournament_foundation"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    required = {
        "winner_manifest": WINNER_DIR / "collector_v1_final_short_horizon_winner_manifest.csv",
        "winner_certification": WINNER_DIR / "collector_v1_final_short_horizon_winner_certification.json",
        "expanded_predictions": first_existing([
            EXPANDED_DIR / "collector_v1_expanded_tournament_predictions.csv",
            EXPANDED_DIR / "collector_v1_expanded_predictions.csv",
        ]),
        "expanded_candidates": first_existing([
            EXPANDED_DIR / "collector_v1_expanded_tournament_candidates.csv",
            EXPANDED_DIR / "collector_v1_expanded_tournament_metrics.csv",
        ]),
        "cohort_predictions": COHORT_DIR / "collector_v1_early_cohort_fallback_predictions.csv",
        "cohort_metrics": COHORT_DIR / "collector_v1_early_cohort_fallback_metrics.csv",
    }

    inventory_rows: list[dict] = []
    missing: list[str] = []
    for role, path in required.items():
        if path is None or not path.exists():
            missing.append(role)
            inventory_rows.append({"authority_role": role, "path": "", "exists": False, "sha256": "", "rows": 0, "columns": ""})
            continue
        rows = 0
        columns = ""
        if path.suffix.lower() == ".csv":
            frame = pd.read_csv(path)
            rows = len(frame)
            columns = "|".join(frame.columns)
        inventory_rows.append({
            "authority_role": role,
            "path": str(path.relative_to(ROOT)),
            "exists": True,
            "sha256": sha256(path),
            "rows": rows,
            "columns": columns,
        })

    inventory = pd.DataFrame(inventory_rows)
    inventory.to_csv(OUT_DIR / "collector_v1_pre_recommendation_authority_inventory.csv", index=False)

    manifest_path = required["winner_manifest"]
    manifest = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
    routes = sorted(manifest["resolved_route"].dropna().astype(str).unique().tolist()) if not manifest.empty else []
    route_penalty_count = int(manifest.get("confidence_penalty_required", pd.Series(dtype=bool)).astype(str).str.lower().eq("true").sum()) if not manifest.empty else 0

    residual_methods = [
        "GLOBAL_EMPIRICAL",
        "ROUTE_HORIZON_EMPIRICAL",
        "ROUTE_HORIZON_RECENCY_WEIGHTED",
        "SIGNED_CONFORMAL",
        "ABSOLUTE_CONFORMAL",
        "HYBRID_ROUTE_CONFORMAL",
    ]
    interval_levels = [0.80, 0.90]
    simulation_methods = [
        "LOG_RETURN_BOOTSTRAP",
        "ROUTE_RESIDUAL_BOOTSTRAP",
        "STUDENT_T_RESIDUAL",
        "BLOCK_BOOTSTRAP",
        "REGIME_MIXTURE",
        "MEAN_REVERTING_DRIFT",
        "CONSERVATIVE_ENSEMBLE",
    ]
    horizons = [1095, 1825]
    scenarios = [
        "BASE",
        "SCARCITY_UPSIDE",
        "SUPPLY_EXPANSION",
        "DEMAND_CONTRACTION",
        "LIQUIDITY_SHOCK",
    ]

    matrix_rows: list[dict] = []
    for method in residual_methods:
        for level in interval_levels:
            matrix_rows.append({"tournament_stage": "RESIDUAL_INTERVAL", "method": method, "horizon_days": "", "scenario": "", "interval_level": level})
    for method in simulation_methods:
        for horizon in horizons:
            for scenario in scenarios:
                matrix_rows.append({"tournament_stage": "LONG_HORIZON_SIMULATION", "method": method, "horizon_days": horizon, "scenario": scenario, "interval_level": ""})
    matrix = pd.DataFrame(matrix_rows)
    matrix.to_csv(OUT_DIR / "collector_v1_pre_recommendation_tournament_matrix.csv", index=False)

    winner_cert = {}
    winner_cert_path = required["winner_certification"]
    if winner_cert_path.exists():
        winner_cert = json.loads(winner_cert_path.read_text(encoding="utf-8"))

    foundation_ready = bool(
        not missing
        and winner_cert.get("final_short_horizon_winners_certified") is True
        and len(manifest) == 13
        and len(routes) >= 3
    )
    summary = {
        "block_name": "Collector V1 Pre-Recommendation Tournament Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "required_authorities": len(required),
        "missing_authorities": missing,
        "short_horizon_manifest_rows": int(len(manifest)),
        "resolved_routes": routes,
        "confidence_penalty_routes": route_penalty_count,
        "residual_methods": residual_methods,
        "interval_levels": interval_levels,
        "simulation_methods": simulation_methods,
        "long_horizon_days": horizons,
        "stress_scenarios": scenarios,
        "minimum_simulations_per_product_horizon": 10000,
        "tournament_cells": int(len(matrix)),
        "foundation_ready": foundation_ready,
        "residual_interval_tournament_authorized": foundation_ready,
        "long_horizon_simulation_tournament_authorized_after_residual_certification": foundation_ready,
        "decision_readiness_tournament_required": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_PRE_RECOMMENDATION_TOURNAMENT_FOUNDATION_READY" if foundation_ready else "FAIL_COLLECTOR_V1_PRE_RECOMMENDATION_TOURNAMENT_FOUNDATION",
    }
    (OUT_DIR / "collector_v1_pre_recommendation_tournament_foundation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (foundation_ready or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
