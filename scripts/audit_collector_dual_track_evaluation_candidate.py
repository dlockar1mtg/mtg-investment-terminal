from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_dual_track_evaluation_candidate_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    cfg = load_json(CONFIG)
    out_dir = ROOT / cfg["outputs"]["directory"]

    required_outputs = [
        "collector_authoritative_universe",
        "collector_retrospective_outcome_history",
        "collector_retrospective_coverage",
        "collector_prospective_decision_snapshot",
        "collector_prospective_snapshot_manifest",
        "collector_dual_track_summary",
    ]
    for key in required_outputs:
        path = out_dir / cfg["outputs"][key]
        if not path.exists():
            failures.append(f"missing_output:{key}:{path}")

    summary = {}
    universe = pd.DataFrame()
    history = pd.DataFrame()
    snapshot = pd.DataFrame()
    manifest = {}
    if not failures:
        summary = load_json(out_dir / cfg["outputs"]["collector_dual_track_summary"])
        manifest = load_json(out_dir / cfg["outputs"]["collector_prospective_snapshot_manifest"])
        universe = pd.read_csv(out_dir / cfg["outputs"]["collector_authoritative_universe"], low_memory=False)
        history = pd.read_csv(out_dir / cfg["outputs"]["collector_retrospective_outcome_history"], low_memory=False)
        snapshot = pd.read_csv(out_dir / cfg["outputs"]["collector_prospective_decision_snapshot"], low_memory=False)

        if universe.empty:
            failures.append("collector_universe_empty")
        if len(universe) >= 100:
            failures.append(f"collector_scope_expanded_beyond_lane:{len(universe)}")
        if universe["canonical_tcgplayer_product_id"].astype("string").duplicated().any():
            failures.append("duplicate_collector_universe_identity")
        if history["canonical_tcgplayer_product_id"].astype("string").isin(set()).any():
            failures.append("unexpected_empty_identity")
        if history["historical_decision_input_eligible"].astype("string").str.lower().isin(["true", "1", "yes"]).any():
            failures.append("retrospective_history_incorrectly_authorized_as_decision_input")
        if not history["knowledge_availability_status"].astype("string").eq("RETROSPECTIVE_AVAILABILITY_UNPROVEN").all():
            failures.append("retrospective_knowledge_status_not_fail_closed")
        if snapshot["snapshot_id"].astype("string").duplicated().any():
            failures.append("duplicate_prospective_snapshot_id")
        if len(snapshot) != len(universe):
            failures.append(f"snapshot_universe_count_mismatch:{len(snapshot)}:{len(universe)}")
        if snapshot["projection_authorized"].astype("string").str.lower().isin(["true", "1", "yes"]).any():
            failures.append("projection_authorized_in_snapshot")
        if snapshot["purchase_recommendation_authorized"].astype("string").str.lower().isin(["true", "1", "yes"]).any():
            failures.append("purchase_authorized_in_snapshot")
        if manifest.get("projection_authorized") is not False:
            failures.append("manifest_projection_authorization_not_false")
        if manifest.get("purchase_recommendation_authorized") is not False:
            failures.append("manifest_purchase_authorization_not_false")

    scope = cfg.get("scope_rules", {})
    for key in [
        "collector_lane_only",
        "pre_collector_products_prohibited",
        "secret_lair_products_prohibited",
        "future_release_products_retained_but_not_investable",
        "unresolved_identity_fails_closed",
        "dynamic_product_count_required",
    ]:
        if scope.get(key) is not True:
            failures.append(f"scope_rule_not_enabled:{key}")

    auth = cfg.get("authorizations", {})
    for key, value in auth.items():
        if value is not False:
            failures.append(f"authorization_must_remain_false:{key}")

    result = {
        "audit_name": "Collector Dual-Track Evaluation Candidate Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "collector_universe_product_count": int(len(universe)) if not universe.empty else 0,
        "retrospective_observation_count": int(len(history)) if not history.empty else 0,
        "retrospective_outcome_eligible_count": int(history["retrospective_outcome_eligible"].astype("string").str.lower().isin(["true", "1", "yes"]).sum()) if not history.empty else 0,
        "historical_decision_input_eligible_count": 0 if history.empty else int(history["historical_decision_input_eligible"].astype("string").str.lower().isin(["true", "1", "yes"]).sum()),
        "prospective_snapshot_product_count": int(len(snapshot)) if not snapshot.empty else 0,
        "prospective_snapshot_complete_count": int(snapshot["snapshot_complete_for_future_evaluation"].astype("string").str.lower().isin(["true", "1", "yes"]).sum()) if not snapshot.empty else 0,
        "future_information_prohibited": bool(cfg.get("retrospective_track", {}).get("future_information_prohibited", False)),
        "historical_snapshot_builder_authorized": bool(auth.get("historical_snapshot_builder_authorized", False)),
        "candidate_projection_authorized": bool(auth.get("candidate_projection_authorized", False)),
        "production_projection_authorized": bool(auth.get("production_projection_authorized", False)),
        "purchase_recommendation_authorized": bool(auth.get("purchase_recommendation_authorized", False)),
        "automatic_model_update_allowed": bool(auth.get("automatic_model_update_allowed", False)),
        "governing_note": "This audit verifies Collector-only scope, retrospective fail-closed treatment, and prospective snapshot capture. It does not certify forecasts or purchases.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
