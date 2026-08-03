from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_historical_foundation_candidate_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    cfg = load_json(CONFIG)
    out_dir = ROOT / cfg["output_directory"]

    for key, value in cfg.get("authorizations", {}).items():
        if bool(value):
            failures.append(f"authorization_must_remain_false:{key}")

    required = cfg.get("required_outputs", [])
    for filename in required:
        if not (out_dir / filename).exists():
            failures.append(f"missing_output:{filename}")

    summary: dict = {}
    if (out_dir / "collector_historical_foundation_summary.json").exists():
        summary = load_json(out_dir / "collector_historical_foundation_summary.json")
        if summary.get("status") != "PASS":
            failures.append("foundation_summary_not_pass")
        if int(summary.get("governed_universe_product_count", 0)) <= 0:
            failures.append("empty_governed_universe")
        if int(summary.get("products_with_any_history_count", 0)) <= 0:
            failures.append("zero_products_with_history_after_normalized_join")
        for key in [
            "historical_foundation_authorized",
            "historical_snapshot_builder_authorized",
            "projection_authorized",
            "purchase_recommendation_authorized",
        ]:
            if bool(summary.get(key)):
                failures.append(f"summary_authorization_must_remain_false:{key}")

    governed_path = out_dir / "collector_governed_historical_observations.csv"
    if governed_path.exists():
        governed = pd.read_csv(governed_path, low_memory=False)
        required_columns = {
            "canonical_tcgplayer_product_id",
            "observation_date",
            "knowledge_available_timestamp",
            "knowledge_availability_class",
            "market_price_numeric",
            "ledger_source",
            "historical_decision_input_eligible",
            "outcome_measurement_eligible",
            "decision_input_exclusion_reason",
            "dedup_key",
        }
        missing = sorted(required_columns - set(governed.columns))
        failures.extend(f"governed_output_missing_column:{column}" for column in missing)
        if not missing:
            if governed["canonical_tcgplayer_product_id"].isna().any():
                failures.append("governed_output_contains_missing_canonical_id")
            if governed["dedup_key"].duplicated().any():
                failures.append("governed_output_contains_duplicate_dedup_key")
            prices = pd.to_numeric(governed["market_price_numeric"], errors="coerce")
            outcome = governed["outcome_measurement_eligible"].astype("string").str.lower().eq("true")
            if (prices[outcome] <= 0).fillna(True).any():
                failures.append("outcome_eligible_rows_have_invalid_price")
            decision = governed["historical_decision_input_eligible"].astype("string").str.lower().eq("true")
            if (~governed.loc[decision, "knowledge_availability_class"].eq("CONTEMPORANEOUS_LIVE")).any():
                failures.append("decision_input_row_not_contemporaneous_live")

    reconciliation_path = out_dir / "collector_identity_reconciliation.csv"
    if reconciliation_path.exists():
        reconciliation = pd.read_csv(reconciliation_path, low_memory=False)
        if reconciliation["canonical_tcgplayer_product_id"].duplicated().any():
            failures.append("identity_reconciliation_duplicate_canonical_id")

    overlap_path = out_dir / "collector_ledger_overlap_summary.json"
    if overlap_path.exists():
        overlap = load_json(overlap_path)
        if overlap.get("relationship_classification") not in {
            "SUPPORTING_IS_SUBSET_OF_PRIMARY",
            "PARTIAL_OVERLAP_REQUIRES_UNION",
            "DISJOINT_SOURCES",
        }:
            failures.append("invalid_ledger_relationship_classification")

    status = "PASS" if not failures else "FAIL"
    result = {
        "audit_name": "Collector Historical Foundation Candidate Audit",
        "audit_version": "1.0.0",
        "status": status,
        "failure_count": len(failures),
        "failures": failures,
        "identity_normalization_required": True,
        "future_information_prohibited": True,
        "historical_foundation_authorized": False,
        "historical_snapshot_builder_authorized": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "governed_universe_product_count": summary.get("governed_universe_product_count"),
        "products_with_any_history_count": summary.get("products_with_any_history_count"),
        "products_with_proven_historical_decision_inputs_count": summary.get(
            "products_with_proven_historical_decision_inputs_count"
        ),
        "governed_observation_count": summary.get("governed_observation_count"),
        "governing_note": "This audit validates consolidated historical-foundation outputs and fail-closed temporal treatment. It does not approve the foundation or authorize forecasts or purchases.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
