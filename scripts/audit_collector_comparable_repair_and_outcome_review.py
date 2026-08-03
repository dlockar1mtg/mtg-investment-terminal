from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_comparable_repair_and_outcome_review_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    out = ROOT / cfg["output_directory"]
    failures: list[str] = []
    required = [
        "collector_repaired_candidate_forecasts.csv",
        "collector_repaired_peer_contributions.csv",
        "collector_normalized_comparable_edges.csv",
        "collector_repaired_route_summary.csv",
        "collector_owner_methodology_review.csv",
        "collector_comparable_repair_and_outcome_review_summary.json",
    ]
    for name in required:
        if not (out / name).exists():
            failures.append(f"missing_output:{name}")

    summary = {}
    forecasts = pd.DataFrame()
    peers = pd.DataFrame()
    if not failures:
        summary = json.loads((out / required[-1]).read_text(encoding="utf-8"))
        forecasts = pd.read_csv(out / required[0], low_memory=False)
        peers = pd.read_csv(out / required[1], low_memory=False)
        if len(forecasts) != 51:
            failures.append(f"unexpected_product_count:{len(forecasts)}")
        for field in ["candidate_projection_authorized", "production_projection_authorized", "purchase_recommendation_authorized"]:
            if forecasts[field].astype(str).str.lower().isin(["true", "1", "yes"]).any():
                failures.append(f"authorization_open_in_forecasts:{field}")
        if not peers.empty:
            invalid_status = peers["decision_input_status"].astype(str) != "RETROSPECTIVE_DIAGNOSTIC_ONLY"
            if invalid_status.any():
                failures.append("peer_decision_input_status_invalid")
        if int(summary.get("used_peer_contribution_count", 0)) <= 0:
            failures.append("no_peer_contributions_used_after_repair")
        if int(summary.get("candidate_calculation_complete_count", 0)) <= 19:
            failures.append("repair_did_not_improve_completion")
        if int(summary.get("owner_validated_price_count", 0)) != 4:
            failures.append("owner_validated_price_count_not_four")

    status = "PASS" if not failures else "FAIL"
    result = {
        "audit_name": "Collector Comparable Repair and Outcome Review Audit",
        "audit_version": "1.0.0",
        "status": status,
        "failure_count": len(failures),
        "failures": failures,
        "product_count": int(len(forecasts)),
        "used_peer_contribution_count": int(summary.get("used_peer_contribution_count", 0)),
        "candidate_calculation_complete_count": int(summary.get("candidate_calculation_complete_count", 0)),
        "candidate_calculation_incomplete_count": int(summary.get("candidate_calculation_incomplete_count", 0)),
        "owner_validated_price_count": int(summary.get("owner_validated_price_count", 0)),
        "future_information_prohibited": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "governing_note": "This audit validates ID normalization, peer contribution use, disclosure, and closed authorizations. It does not certify forecast accuracy or purchases."
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
