from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_methodology_adjustment_trace_and_final_ballot_v1.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    capture_root = ROOT / cfg["inputs"]["decision_capture_root"]
    reconciliation_root = ROOT / cfg["inputs"]["reconciliation_root"]
    owner_root = ROOT / cfg["inputs"]["owner_decision_root"]
    out = ROOT / cfg["output_directory"]
    out.mkdir(parents=True, exist_ok=True)

    inputs = {
        "adjustments": capture_root / "collector_comparable_baseline_adjustment_reconciliation.csv",
        "forecasts": reconciliation_root / "collector_reconciled_candidate_forecasts.csv",
        "ballot": capture_root / "collector_methodology_owner_decision_ballot.csv",
        "recommendations": owner_root / "collector_methodology_owner_decision_register.csv",
    }
    failures = [f"missing_input:{name}:{path}" for name, path in inputs.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    adjustments = pd.read_csv(inputs["adjustments"], low_memory=False)
    forecasts = pd.read_csv(inputs["forecasts"], low_memory=False)
    ballot = pd.read_csv(inputs["ballot"], low_memory=False)
    recommendations = pd.read_csv(inputs["recommendations"], low_memory=False)

    comparable = forecasts[forecasts["forecast_method_route"].astype(str) == "COMPARABLE_PRODUCT_ADJUSTED"].copy()
    keep = [
        "canonical_tcgplayer_product_id",
        "product_name",
        "fundamental_adjustment_annual_rate",
        "base_annual_rate",
        "comparable_component_annual_rate",
    ]
    comparable = comparable[[c for c in keep if c in comparable.columns]].copy()

    traced = adjustments.merge(
        comparable,
        on=["canonical_tcgplayer_product_id", "product_name"],
        how="left",
        suffixes=("", "_forecast"),
    )
    traced["unresolved_non_peer_adjustment"] = pd.to_numeric(
        traced["unresolved_non_peer_adjustment"], errors="coerce"
    )
    traced["fundamental_adjustment_annual_rate"] = pd.to_numeric(
        traced.get("fundamental_adjustment_annual_rate"), errors="coerce"
    )
    traced["unexplained_residual_after_fundamental"] = (
        traced["unresolved_non_peer_adjustment"]
        - traced["fundamental_adjustment_annual_rate"].fillna(0.0)
    )
    traced["fundamental_match_within_tolerance"] = (
        traced["unexplained_residual_after_fundamental"].abs() <= 1e-10
    )
    traced["adjustment_trace_status"] = traced["fundamental_match_within_tolerance"].map(
        lambda v: "MATCHES_RECONCILED_FUNDAMENTAL_ADJUSTMENT" if bool(v)
        else "UNEXPLAINED_RESIDUAL_REQUIRES_SOURCE_REVIEW"
    )
    traced["adjustment_authorized"] = False
    traced.to_csv(out / "collector_comparable_adjustment_trace.csv", index=False)

    group_summary = (
        traced.assign(
            adjustment_rounded=traced["unresolved_non_peer_adjustment"].round(4),
            fundamental_rounded=traced["fundamental_adjustment_annual_rate"].round(4),
            residual_rounded=traced["unexplained_residual_after_fundamental"].round(10),
        )
        .groupby(["adjustment_rounded", "fundamental_rounded", "residual_rounded", "adjustment_trace_status"], dropna=False)
        .agg(
            product_count=("product_name", "count"),
            product_examples=("product_name", lambda s: " | ".join(list(s.astype(str))[:5])),
        )
        .reset_index()
    )
    group_summary.to_csv(out / "collector_comparable_adjustment_trace_groups.csv", index=False)

    final_ballot = ballot.copy()
    if "nonbinding_recommendation" not in final_ballot.columns and "decision_id" in recommendations.columns:
        final_ballot = final_ballot.merge(
            recommendations[["decision_id", "nonbinding_recommendation"]],
            on="decision_id",
            how="left",
        )
    final_ballot["owner_decision_status"] = final_ballot.get("owner_decision_status", "PENDING_OWNER_DECISION").fillna("PENDING_OWNER_DECISION")
    final_ballot["owner_selected_option"] = final_ballot.get("owner_selected_option", "").fillna("")
    final_ballot["owner_rationale"] = final_ballot.get("owner_rationale", "").fillna("")
    final_ballot["activation_authorized"] = False
    final_ballot["adjustment_trace_complete"] = bool(traced["fundamental_match_within_tolerance"].all())
    final_ballot.to_csv(out / "collector_methodology_final_owner_ballot.csv", index=False)

    all_matches = bool(traced["fundamental_match_within_tolerance"].all())
    pending_count = int((final_ballot["owner_selected_option"].astype(str).str.strip() == "").sum())
    final_spec = {
        "specification_name": "Collector Final Inactive Methodology Ballot",
        "specification_version": "1.0.0",
        "status": "INACTIVE_OWNER_DECISION_REQUIRED",
        "baseline_adjustment_trace_complete": all_matches,
        "baseline_adjustment_interpretation": (
            "MATCHES_RECONCILED_FUNDAMENTAL_ADJUSTMENT_FIELD"
            if all_matches else "PARTIALLY_UNEXPLAINED_SOURCE_REVIEW_REQUIRED"
        ),
        "all_six_owner_decisions_complete": pending_count == 0,
        "pending_owner_decision_count": pending_count,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
    }
    (out / "collector_methodology_final_inactive_specification.json").write_text(
        json.dumps(final_spec, indent=2, sort_keys=True), encoding="utf-8"
    )

    result = {
        "audit_name": "Collector Methodology Adjustment Trace and Final Ballot",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(forecasts)),
        "comparable_product_count": int(len(traced)),
        "fundamental_match_count": int(traced["fundamental_match_within_tolerance"].sum()),
        "unexplained_residual_count": int((~traced["fundamental_match_within_tolerance"]).sum()),
        "decision_count": int(len(final_ballot)),
        "pending_owner_decision_count": pending_count,
        "baseline_adjustment_trace_complete": all_matches,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": 0,
        "failures": [],
        "governing_note": "This batch traces the comparable-route baseline adjustment to the reconciled fundamental-adjustment field where supported and produces a final inactive six-decision ballot. It does not infer owner decisions or authorize forecasts or purchases.",
    }
    (out / "collector_methodology_adjustment_trace_and_final_ballot_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
