from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_v2_4_confidence_decision_owner_review_v1.json"
SOURCE = ROOT / "data/operations/collector_candidate_v2_4_prospective_calibration_tournament/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_candidate_v2_4_confidence_decision_owner_review/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    conf = pd.read_csv(SOURCE / "collector_candidate_v2_4_prospective_confidence_summary.csv", low_memory=False)
    dec = pd.read_csv(SOURCE / "collector_candidate_v2_4_decision_threshold_summary.csv", low_memory=False)

    rows = []
    for horizon in [90, 180, 365]:
        rec = cfg["confidence_recommendations"].get(f"{horizon}_day", {})
        method = rec.get("method", "")
        match = conf[(conf["horizon_days"].astype(int) == horizon) & (conf["confidence_method"] == method)]
        rows.append({
            "horizon_days": horizon,
            "confidence_recommendation": rec.get("recommended_structure", "REMAIN_UNCERTIFIED"),
            "confidence_method": method,
            "confidence_evidence_available": not match.empty,
            "aggregate_ordering_pass": bool(match.iloc[0]["ordinal_error_ordering_pass"]) if not match.empty else False,
            "low_minus_high_mae_spread": float(match.iloc[0]["low_minus_high_mae_spread"]) if not match.empty else None,
            "confidence_authorized": False,
        })
    confidence_review = pd.DataFrame(rows)

    decision_rows = []
    for horizon in [90, 180, 365]:
        rec = cfg["decision_state_recommendations"].get(f"{horizon}_day", {})
        lower = rec.get("lower_quantile")
        upper = rec.get("upper_quantile")
        if lower is not None and upper is not None:
            match = dec[
                (dec["horizon_days"].astype(int) == horizon)
                & (dec["lower_quantile"].astype(float) == float(lower))
                & (dec["upper_quantile"].astype(float) == float(upper))
            ]
        else:
            match = pd.DataFrame()
        decision_rows.append({
            "horizon_days": horizon,
            "decision_recommendation": rec.get("recommended_status", "REMAIN_UNCERTIFIED"),
            "lower_quantile": lower,
            "upper_quantile": upper,
            "decision_evidence_available": not match.empty,
            "ordinal_ordering_pass": bool(match.iloc[0]["ordinal_realized_ordering_pass"]) if not match.empty else False,
            "decision_method_authorized": False,
        })
    decision_review = pd.DataFrame(decision_rows)

    failures = []
    if confidence_review.empty:
        failures.append("confidence_review_empty")
    if decision_review.empty:
        failures.append("decision_review_empty")
    for key in [
        "prospective_confidence_method_authorized",
        "decision_state_method_authorized",
        "candidate_methodology_change_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
        "technical_freeze_authorized",
        "uip_acceptance_authorized",
    ]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    confidence_review.to_csv(OUT / "collector_candidate_v2_4_confidence_owner_review.csv", index=False)
    decision_review.to_csv(OUT / "collector_candidate_v2_4_decision_owner_review.csv", index=False)
    result = {
        "review_name": cfg["review_name"],
        "review_version": cfg["review_version"],
        "status": "PASS" if not failures else "FAIL",
        "confidence_review_count": int(len(confidence_review)),
        "decision_review_count": int(len(decision_review)),
        "owner_approval_required": True,
        "prospective_confidence_method_authorized": False,
        "decision_state_method_authorized": False,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_candidate_v2_4_confidence_decision_owner_review_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
