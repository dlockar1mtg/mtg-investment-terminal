from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_methodology_owner_decision_package_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_json(CONFIG)
    sensitivity_root = ROOT / cfg["inputs"]["sensitivity_root"]
    evidence_root = ROOT / cfg["inputs"]["evidence_root"]
    reconciliation_root = ROOT / cfg["inputs"]["reconciliation_root"]
    out_dir = ROOT / cfg["output_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "sensitivity_review": sensitivity_root / "collector_methodology_sensitivity_product_review.csv",
        "variants": sensitivity_root / "collector_methodology_sensitivity_variants.csv",
        "sensitivity_decisions": sensitivity_root / "collector_methodology_sensitivity_owner_decisions.csv",
        "evidence_review": evidence_root / "collector_methodology_product_review.csv",
        "route_risk": evidence_root / "collector_route_risk_summary.csv",
        "forecasts": reconciliation_root / "collector_reconciled_candidate_forecasts.csv",
    }
    failures = [f"missing_input:{name}:{path}" for name, path in paths.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    sensitivity = pd.read_csv(paths["sensitivity_review"], low_memory=False)
    variants = pd.read_csv(paths["variants"], low_memory=False)
    decisions = pd.read_csv(paths["sensitivity_decisions"], low_memory=False)
    evidence = pd.read_csv(paths["evidence_review"], low_memory=False)
    route_risk = pd.read_csv(paths["route_risk"], low_memory=False)
    forecasts = pd.read_csv(paths["forecasts"], low_memory=False)

    for frame in [sensitivity, variants, evidence, forecasts]:
        if "canonical_tcgplayer_product_id" in frame.columns:
            frame["canonical_tcgplayer_product_id"] = frame["canonical_tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)

    sensitivity["variant_spread"] = numeric(sensitivity["variant_spread"])
    sensitivity["baseline_base_annual_rate"] = numeric(sensitivity["baseline_base_annual_rate"])
    review = sensitivity.copy()
    review["recommended_peer_aggregation_candidate"] = np.where(
        review["forecast_method_route"].isin(["COMPARABLE_PRODUCT_ADJUSTED", "DIRECT_HISTORY_LIMITED"]),
        "PEER_TRIMMED_MEAN_10_PERCENT",
        "BASELINE_ROUTE_METHOD",
    )
    review["recommended_short_history_candidate"] = np.where(
        review["forecast_method_route"].eq("DIRECT_HISTORY_LIMITED"),
        "SIMPLE_RETURN_UNTIL_365_DAYS_OBSERVED",
        "NOT_APPLICABLE",
    )
    review["recommended_dominant_peer_candidate"] = np.where(
        review.get("high_peer_concentration_flag", False).map(truthy),
        "REQUIRE_REVIEW_AND_EXCLUDE_IF_WEIGHT_EXCEEDS_APPROVED_THRESHOLD",
        "NO_AUTOMATIC_EXCLUSION",
    )
    review["recommended_extreme_rate_candidate"] = np.where(
        review.get("extreme_base_rate_flag", False).map(truthy),
        "DISCLOSE_AND_REQUIRE_OWNER_REVIEW_NO_AUTOMATIC_CLIP",
        "NO_SPECIAL_TREATMENT",
    )
    review["recommended_symmetric_score_candidate"] = np.where(
        review.get("reverse_pair_candidate_used", False).map(truthy),
        "ALLOW_FOR_DIAGNOSTICS_ONLY_PENDING_PROSPECTIVE_VALIDATION",
        "NOT_APPLICABLE",
    )
    review["recommended_japanese_hybrid_candidate"] = np.where(
        review["forecast_method_route"].eq("FUNDAMENTAL_COMPARABLE_HYBRID"),
        "KEEP_PRIMARY_COMPARABLE_OVERRIDE_FORMULA_STILL_PENDING",
        "NOT_APPLICABLE",
    )
    review["recommendation_status"] = "NONBINDING_CANDIDATE_REQUIRES_OWNER_APPROVAL"
    review["candidate_projection_authorized"] = False
    review["production_projection_authorized"] = False
    review["purchase_recommendation_authorized"] = False

    product_cols = [
        "canonical_tcgplayer_product_id", "product_name", "forecast_method_route",
        "baseline_base_annual_rate", "variant_min_annual_rate", "variant_max_annual_rate",
        "variant_spread", "short_history_flag", "extreme_base_rate_flag",
        "negative_base_rate_flag", "high_peer_concentration_flag",
        "reverse_pair_candidate_used", "recommended_peer_aggregation_candidate",
        "recommended_short_history_candidate", "recommended_dominant_peer_candidate",
        "recommended_extreme_rate_candidate", "recommended_symmetric_score_candidate",
        "recommended_japanese_hybrid_candidate", "recommendation_status",
        "candidate_projection_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized",
    ]
    product_review = review[[c for c in product_cols if c in review.columns]].copy()
    product_review.to_csv(out_dir / "collector_methodology_owner_product_recommendations.csv", index=False)

    decision_rows = [
        {
            "decision_id": "COL-METH-001",
            "topic": "Symmetric comparable-score reuse",
            "evidence_summary": "Seven limited-history products require reversed existing pair scores for complete comparable diagnostics.",
            "nonbinding_recommendation": "Allow reversed scores for diagnostics only; do not activate for production until prospective validation supports the assumption.",
            "owner_decision_status": "PENDING_OWNER_DECISION",
        },
        {
            "decision_id": "COL-METH-002",
            "topic": "Short-history annualization",
            "evidence_summary": "Simple and annualized returns diverge on short histories and can produce unstable rates.",
            "nonbinding_recommendation": "Use simple return until at least 365 observed days; then permit annualization subject to minimum observation standards.",
            "owner_decision_status": "PENDING_OWNER_DECISION",
        },
        {
            "decision_id": "COL-METH-003",
            "topic": "Peer aggregation method",
            "evidence_summary": "Twenty-nine products are sensitivity-review candidates and many comparable routes move materially between weighted mean, median, trimmed mean, and top-five methods.",
            "nonbinding_recommendation": "Use 10% trimmed peer mean as the next candidate default; retain weighted mean and median as required disclosures.",
            "owner_decision_status": "PENDING_OWNER_DECISION",
        },
        {
            "decision_id": "COL-METH-004",
            "topic": "Dominant-peer treatment",
            "evidence_summary": "One product exceeds the current diagnostic concentration flag, while Spider-Man shows material dominant-peer sensitivity despite not crossing that threshold.",
            "nonbinding_recommendation": "Require explicit concentration disclosure and owner review before excluding a dominant peer; do not silently remove peers.",
            "owner_decision_status": "PENDING_OWNER_DECISION",
        },
        {
            "decision_id": "COL-METH-005",
            "topic": "Extreme annual-rate treatment",
            "evidence_summary": "Edge of Eternities and regular Lord of the Rings exceed the current 100% diagnostic review threshold.",
            "nonbinding_recommendation": "Do not clip automatically; require disclosure, sensitivity range, and owner review before production use.",
            "owner_decision_status": "PENDING_OWNER_DECISION",
        },
        {
            "decision_id": "COL-METH-006",
            "topic": "Japanese FINAL FANTASY hybrid numeric methodology",
            "evidence_summary": "The approved primary comparable is stable across peer variants, but the formula remains negative and the hybrid weights are not approved.",
            "nonbinding_recommendation": "Keep the primary comparable override; keep the formula inactive until language-liquidity and fundamental-weight review is complete.",
            "owner_decision_status": "COMPARABLE_APPROVED_FORMULA_PENDING",
        },
    ]
    decision_df = pd.DataFrame(decision_rows)
    decision_df["candidate_projection_authorized"] = False
    decision_df["production_projection_authorized"] = False
    decision_df["purchase_recommendation_authorized"] = False
    decision_df.to_csv(out_dir / "collector_methodology_owner_decision_register.csv", index=False)

    route_package = route_risk.copy()
    route_package["nonbinding_route_recommendation"] = route_package["forecast_method_route"].map({
        "DIRECT_HISTORY_CALIBRATED": "PRESERVE_BASELINE_PENDING_EXTREME_RATE_REVIEW",
        "DIRECT_HISTORY_LIMITED": "USE_SIMPLE_HISTORY_PLUS_TRIMMED_PEERS_AS_NEXT_CANDIDATE",
        "COMPARABLE_PRODUCT_ADJUSTED": "USE_TRIMMED_PEER_MEAN_AS_NEXT_CANDIDATE",
        "FUNDAMENTAL_COMPARABLE_HYBRID": "KEEP_INACTIVE_PENDING_FORMULA_REVIEW",
    }).fillna("REVIEW_REQUIRED")
    route_package["recommendation_status"] = "NONBINDING_CANDIDATE_REQUIRES_OWNER_APPROVAL"
    route_package.to_csv(out_dir / "collector_methodology_owner_route_recommendations.csv", index=False)

    recommended_spec = {
        "specification_name": "Collector Recommended Candidate Methodology",
        "specification_version": "1.0.0",
        "status": "RECOMMENDED_INACTIVE_OWNER_REVIEW_REQUIRED",
        "peer_aggregation_candidate": "PEER_TRIMMED_MEAN_10_PERCENT",
        "short_history_candidate": "SIMPLE_RETURN_UNTIL_365_DAYS_OBSERVED",
        "symmetric_score_candidate": "DIAGNOSTIC_ONLY_PENDING_PROSPECTIVE_VALIDATION",
        "dominant_peer_candidate": "DISCLOSE_AND_REQUIRE_REVIEW_NO_AUTOMATIC_EXCLUSION",
        "extreme_rate_candidate": "DISCLOSE_AND_REQUIRE_REVIEW_NO_AUTOMATIC_CLIP",
        "japanese_final_fantasy": {
            "primary_comparable_status": "OWNER_APPROVED",
            "formula_status": "PENDING_OWNER_APPROVAL"
        },
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False
    }
    (out_dir / "collector_recommended_candidate_methodology.json").write_text(
        json.dumps(recommended_spec, indent=2, sort_keys=True), encoding="utf-8"
    )

    summary = {
        "audit_name": "Collector Methodology Owner Decision Package",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(product_review)),
        "route_count": int(route_package["forecast_method_route"].nunique()),
        "decision_count": int(len(decision_df)),
        "sensitivity_review_required_product_count": int(sensitivity.get("sensitivity_review_required", False).map(truthy).sum()),
        "short_history_product_count": int(sensitivity.get("short_history_flag", False).map(truthy).sum()),
        "extreme_rate_product_count": int(sensitivity.get("extreme_base_rate_flag", False).map(truthy).sum()),
        "negative_rate_product_count": int(sensitivity.get("negative_base_rate_flag", False).map(truthy).sum()),
        "recommended_specification_status": recommended_spec["status"],
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "future_information_prohibited": True,
        "failure_count": 0,
        "failures": [],
        "governing_note": "This package converts sensitivity evidence into nonbinding recommendations for owner review. It does not approve or activate any methodology, forecast, purchase recommendation, or automatic update."
    }
    (out_dir / "collector_methodology_owner_decision_package_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
