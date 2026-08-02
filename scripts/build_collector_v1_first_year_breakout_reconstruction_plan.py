from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
FOUNDATION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation"
FOUNDATION = FOUNDATION_DIR / "collector_v1_august1_snapshot_bound_current_foundation.csv"
FOUNDATION_CERT = FOUNDATION_DIR / "collector_v1_august1_snapshot_bound_current_foundation_certification.json"
CONTRACT = ROOT / "config/mtg/standards/collector_first_year_breakout_entry_timing_contract_v1.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_first_year_breakout_reconstruction_plan"
KEY = "tcgplayer_product_id"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    generated = datetime.now(timezone.utc).isoformat()

    missing = [str(path.relative_to(ROOT)) for path in (FOUNDATION, FOUNDATION_CERT, CONTRACT) if not path.is_file()]
    OUT.mkdir(parents=True, exist_ok=True)
    if missing:
        summary = {
            "block_name": "Collector V1 First-Year Breakout Reconstruction Plan",
            "generated_at_utc": generated,
            "critical_failures": [f"missing_required_files:{'|'.join(missing)}"],
            "status": "FAIL_COLLECTOR_V1_FIRST_YEAR_BREAKOUT_RECONSTRUCTION_INPUTS_MISSING",
        }
        (OUT / "collector_v1_first_year_breakout_reconstruction_plan_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    foundation = read_csv(FOUNDATION)
    cert = read_json(FOUNDATION_CERT)
    contract = read_json(CONTRACT)
    checkpoints = list(contract["evaluation_checkpoints_days"])
    name_col = "product_name" if "product_name" in foundation.columns else "canonical_product_name"

    rows: list[dict] = []
    for _, product in foundation.iterrows():
        product_id = str(product[KEY]).strip()
        comparable_route = str(product.get("forecast_route", "")) in {
            "COMPARABLE_PRODUCT_ADJUSTED",
            "FUNDAMENTAL_COMPARABLE_HYBRID",
            "EARLY_OPPORTUNITY_COHORT_FALLBACK",
        }
        for checkpoint in checkpoints:
            rows.append({
                KEY: product_id,
                "product_name": str(product.get(name_col, "")),
                "checkpoint_age_days": int(checkpoint),
                "point_in_time_replay_required": True,
                "future_information_prohibited": True,
                "release_age_alignment_required": True,
                "comparable_selection_as_of_checkpoint_required": True,
                "supply_demand_as_of_checkpoint_required": True,
                "breakout_definition_tournament_required": True,
                "breakout_model_tournament_required": True,
                "entry_timing_model_required": True,
                "false_positive_measurement_required": True,
                "missed_entry_cost_required": True,
                "opportunity_capture_required": True,
                "late_signal_penalty_required": True,
                "comparable_route": comparable_route,
                "selected_comparable_paths_required": comparable_route,
                "mtg_owned_output": True,
                "uip_may_rewrite_output": False,
                "purchase_recommendation_authorized": False,
                "source_snapshot_id": str(product.get("source_snapshot_id", "")),
            })

    matrix = pd.DataFrame(rows)
    matrix_path = OUT / "collector_v1_first_year_breakout_reconstruction_matrix.csv"
    matrix.to_csv(matrix_path, index=False)

    required_metrics = set(contract["required_metrics"])
    required_states = set(contract["required_states"])
    required_outputs = set(contract["required_product_outputs"])
    checks = {
        "foundation_certified": cert.get("current_foundation_certified") is True,
        "foundation_has_50_products": len(foundation) == 50,
        "foundation_product_ids_unique": bool(foundation[KEY].is_unique),
        "eight_checkpoints_present": checkpoints == [0, 30, 60, 90, 120, 180, 270, 365],
        "all_400_product_checkpoint_rows_present": len(matrix) == 400,
        "all_products_receive_all_checkpoints": bool(matrix.groupby(KEY)["checkpoint_age_days"].nunique().eq(8).all()),
        "point_in_time_replay_required": bool(matrix["point_in_time_replay_required"].all()),
        "future_information_prohibited": bool(matrix["future_information_prohibited"].all()),
        "all_rows_require_breakout_tournament": bool(matrix["breakout_model_tournament_required"].all()),
        "all_rows_require_entry_timing": bool(matrix["entry_timing_model_required"].all()),
        "all_rows_require_missed_entry_cost": bool(matrix["missed_entry_cost_required"].all()),
        "all_rows_require_opportunity_capture": bool(matrix["opportunity_capture_required"].all()),
        "all_rows_require_late_signal_penalty": bool(matrix["late_signal_penalty_required"].all()),
        "all_outputs_owned_by_mtg": bool(matrix["mtg_owned_output"].all()),
        "uip_cannot_rewrite_outputs": bool(matrix["uip_may_rewrite_output"].eq(False).all()),
        "purchase_recommendations_remain_unauthorized": bool(matrix["purchase_recommendation_authorized"].eq(False).all()),
        "all_snapshot_ids_match": bool(matrix["source_snapshot_id"].eq(SNAPSHOT_ID).all()),
        "required_discovery_metrics_present": {
            "breakout_recall", "early_entry_precision", "median_signal_lead_days",
            "missed_entry_cost_pct", "opportunity_capture_pct",
            "appreciation_already_realized_pct", "remaining_expected_upside_pct",
        }.issubset(required_metrics),
        "late_opportunity_states_present": {
            "LATE_STAGE_MOMENTUM", "OPPORTUNITY_MOSTLY_REALIZED", "OVEREXTENDED"
        }.issubset(required_states),
        "required_current_outputs_present": {
            "first_year_breakout_probability", "early_opportunity_score", "entry_timing_status",
            "missed_entry_cost_pct", "price_appreciation_already_realized_pct",
            "remaining_expected_upside_pct", "late_entry_risk",
        }.issubset(required_outputs),
        "fixed_single_breakout_threshold_prohibited": contract["breakout_label_policy"]["fixed_single_threshold_prohibited"] is True,
        "breakout_definitions_compete": contract["breakout_label_policy"]["candidate_definitions_must_compete"] is True,
    }
    failures = [key for key, value in checks.items() if not bool(value)]
    passed = not failures
    summary = {
        "block_name": "Collector V1 First-Year Breakout Reconstruction Plan",
        "block_version": "1.0.0",
        "governing_contract": f"{contract['contract_name']} v{contract['contract_version']}",
        "generated_at_utc": generated,
        "source_snapshot_id": SNAPSHOT_ID,
        "foundation_sha256": sha256(FOUNDATION),
        "contract_sha256": sha256(CONTRACT),
        "matrix_path": str(matrix_path.relative_to(ROOT)),
        "matrix_sha256": sha256(matrix_path),
        "governed_product_count": int(foundation[KEY].nunique()),
        "evaluation_checkpoints_days": checkpoints,
        "product_checkpoint_rows": len(matrix),
        "required_metric_count": len(required_metrics),
        "required_state_count": len(required_states),
        "required_product_output_count": len(required_outputs),
        "checks": {key: bool(value) for key, value in checks.items()},
        "critical_failures": failures,
        "lifecycle_panel_reconstruction_authorized": passed,
        "breakout_model_execution_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_V1_FIRST_YEAR_BREAKOUT_RECONSTRUCTION_PLAN" if passed else "FAIL_COLLECTOR_V1_FIRST_YEAR_BREAKOUT_RECONSTRUCTION_PLAN",
    }
    (OUT / "collector_v1_first_year_breakout_reconstruction_plan_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
