from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_v2_peer_set_audit/candidate_v1_0_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT / "collector_candidate_v2_peer_set_audit_summary.json"
    detail_path = OUT / "collector_candidate_v2_peer_set_detail.csv"
    groups_path = OUT / "collector_candidate_v2_peer_set_groups.csv"
    missing = [str(p) for p in [summary_path, detail_path, groups_path] if not p.exists()]
    if missing:
        result = {"status": "FAIL", "failures": [f"missing_output:{p}" for p in missing]}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    build = json.loads(summary_path.read_text(encoding="utf-8"))
    detail = pd.read_csv(detail_path, low_memory=False)
    failures = []
    if len(detail) != 31:
        failures.append("detail_target_count_not_31")
    if int(detail["peer_set_sha256"].nunique()) < 2:
        failures.append("peer_sets_not_target_diverse")
    if not detail["trimmed_mean_matches"].map(truthy).all():
        failures.append("trimmed_mean_lineage_mismatch")
    if truthy(build.get("global_pool_collapse_detected")):
        failures.append("global_pool_collapse_detected")
    if truthy(build.get("production_projection_authorized")) or truthy(build.get("purchase_recommendation_authorized")):
        failures.append("authorization_boundary_violated")

    result = {
        "audit_name": "Collector Candidate v2 Peer-Set Diversity Audit Verification",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "target_count": int(len(detail)),
        "unique_peer_set_count": int(detail["peer_set_sha256"].nunique()),
        "unique_peer_return_set_count": int(detail["peer_return_set_sha256"].nunique()),
        "unique_trimmed_mean_count": int(detail["recomputed_trimmed_mean_10_percent"].round(12).nunique()),
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
