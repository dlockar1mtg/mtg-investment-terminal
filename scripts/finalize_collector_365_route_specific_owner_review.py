from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_365_route_specific_owner_review_v1.json"
QUAL_ROOT = ROOT / "data/operations/collector_365_final_qualification/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_365_route_specific_owner_review/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    route_path = QUAL_ROOT / "collector_365_final_qualification_route_stability.csv"
    summary_path = QUAL_ROOT / "collector_365_final_qualification_summary.csv"
    routes = pd.read_csv(route_path, low_memory=False) if route_path.exists() else pd.DataFrame()
    summary = pd.read_csv(summary_path, low_memory=False) if summary_path.exists() else pd.DataFrame()
    if routes.empty:
        failures.append("route_stability_missing_or_empty")
    if summary.empty:
        failures.append("qualification_summary_missing_or_empty")

    review_rows: list[dict[str, object]] = []
    for route, rec in cfg["recommendation"].items():
        selected = pd.DataFrame()
        if not routes.empty and rec["method"] != "BLOCKED":
            selected = routes[
                (routes["product_age_route"].astype(str) == route)
                & (routes["method"].astype(str) == rec["method"])
                & (pd.to_numeric(routes["bias_shrinkage"], errors="coerce") == float(rec["bias_shrinkage"]))
            ]
        row = selected.iloc[0].to_dict() if not selected.empty else {}
        review_rows.append({
            "product_age_route": route,
            "recommended_method": rec["method"],
            "recommended_variant": rec["variant"],
            "bias_shrinkage": rec["bias_shrinkage"],
            "evidence_grade": rec["evidence_grade"],
            "owner_review_eligible": bool(rec["owner_review_eligible"]),
            "case_count": row.get("case_count"),
            "cutoff_count": row.get("cutoff_count"),
            "mae": row.get("mae"),
            "signed_bias": row.get("signed_bias"),
            "rank_correlation": row.get("rank_correlation"),
            "top_bottom_spread": row.get("top_bottom_spread"),
            "shadow_implementation_authorized": False,
        })

    review = pd.DataFrame(review_rows)
    review.to_csv(OUT / "collector_365_route_specific_owner_review.csv", index=False)

    for key in [
        "route_specific_shadow_implementation_authorized",
        "direct_method_authorized",
        "comparable_transfer_method_authorized",
        "limited_route_authorized",
        "candidate_methodology_change_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
        "technical_freeze_authorized",
        "uip_acceptance_authorized",
    ]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": cfg["program_name"],
        "audit_version": cfg["program_version"],
        "status": "PASS" if not failures else "FAIL",
        "route_review_count": int(len(review)),
        "owner_review_eligible_route_count": int(review["owner_review_eligible"].sum()) if not review.empty else 0,
        "blocked_route_count": int((review["recommended_method"] == "BLOCKED").sum()) if not review.empty else 0,
        "owner_approval_required": True,
        "route_specific_shadow_implementation_authorized": False,
        "direct_method_authorized": False,
        "comparable_transfer_method_authorized": False,
        "limited_route_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_365_route_specific_owner_review_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
