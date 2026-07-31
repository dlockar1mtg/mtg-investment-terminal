from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_deep_history_recovery_candidate_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    out_dir = ROOT / cfg["candidate_output_directory"]
    for name in cfg["required_outputs"]:
        if not (out_dir / name).exists():
            failures.append(f"missing_output:{name}")
    summary_path = out_dir / "collector_deep_history_recovery_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    for key, value in cfg.get("authorizations", {}).items():
        if bool(value):
            failures.append(f"authorization_must_remain_false:{key}")
    principles = cfg.get("governing_principles", {})
    for key, value in principles.items():
        if not bool(value):
            failures.append(f"governing_principle_not_enabled:{key}")
    candidate_path = out_dir / "collector_deep_history_candidate.csv"
    if candidate_path.exists():
        df = pd.read_csv(candidate_path, low_memory=False)
        required_cols = {
            "canonical_tcgplayer_product_id",
            "observation_date",
            "market_price",
            "source_file",
            "knowledge_availability_status",
            "historical_decision_input_eligible",
            "outcome_measurement_eligible",
            "dedup_key",
        }
        missing = required_cols - set(df.columns)
        failures.extend(f"candidate_missing_column:{col}" for col in sorted(missing))
        if "historical_decision_input_eligible" in df.columns:
            values = df["historical_decision_input_eligible"].astype("string").str.lower()
            if values.isin(["true", "1", "yes"]).any():
                failures.append("historical_input_authorized_without_proven_availability")
        if "dedup_key" in df.columns and df["dedup_key"].duplicated().any():
            failures.append("duplicate_dedup_key_present")
    status = "PASS" if not failures else "FAIL"
    result = {
        "audit_name": "Collector Deep History Recovery Candidate Audit",
        "audit_version": "1.0.0",
        "status": status,
        "failure_count": len(failures),
        "failures": failures,
        "governed_product_count": summary.get("governed_product_count", 0),
        "product_with_release_date_count": summary.get("product_with_release_date_count", 0),
        "history_source_present_count": summary.get("history_source_present_count", 0),
        "deep_history_source_count": summary.get("deep_history_source_count", 0),
        "deep_history_observation_count": summary.get("deep_history_observation_count", 0),
        "products_with_deep_history_count": summary.get("products_with_deep_history_count", 0),
        "historical_snapshot_builder_authorized": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "future_information_prohibited": bool(principles.get("future_information_prohibited", False)),
        "governing_note": "This audit validates recovery outputs and fail-closed treatment only. It does not authorize recovered history as historical decision input.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
