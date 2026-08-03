from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_v2_3_final_validation_v1.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    inputs = cfg["inputs"]
    candidate_root = ROOT / inputs["candidate_root"]
    forecasts_path = candidate_root / inputs["candidate_forecasts"]
    summary_path = candidate_root / inputs["candidate_summary"]
    approval_path = ROOT / inputs["candidate_approval"]
    builder_path = ROOT / inputs["candidate_builder"]
    audit_path = ROOT / inputs["candidate_audit"]
    required = [forecasts_path, summary_path, approval_path, builder_path, audit_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        result = {"status": "FAIL", "failure_count": len(missing), "failures": [f"missing_input:{path}" for path in missing]}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(forecasts_path, low_memory=False)
    candidate_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expectations = cfg["expectations"]

    complete = forecasts["candidate_v2_3_calculation_complete"].map(truthy)
    reverse = forecasts["candidate_v2_3_method_status"].astype(str).str.startswith("DIAGNOSTIC_ONLY_REVERSE_SCORE")
    hybrid = forecasts["candidate_v2_3_method_status"].astype(str).eq("FORMULA_INACTIVE_OWNER_DECISION")
    downside = pd.to_numeric(forecasts["candidate_v2_3_downside_annual_rate"], errors="coerce")
    confidence = pd.to_numeric(forecasts["candidate_v2_3_confidence_score_0_to_100"], errors="coerce")

    exception_rows = []
    for _, row in forecasts.iterrows():
        status = str(row.get("candidate_v2_3_method_status", ""))
        reasons: list[str] = []
        if status.startswith("DIAGNOSTIC_ONLY_REVERSE_SCORE"):
            reasons.append("REVERSE_SCORE_ROUTE_NOT_PRODUCTION_ELIGIBLE")
        if status == "FORMULA_INACTIVE_OWNER_DECISION":
            reasons.append("JAPANESE_HYBRID_FORMULA_INACTIVE")
        rate = pd.to_numeric(pd.Series([row.get("candidate_v2_3_base_annual_rate")]), errors="coerce").iloc[0]
        if pd.notna(rate) and float(rate) >= 0.75:
            reasons.append("HIGH_ANNUAL_RATE_REVIEW")
        if pd.notna(rate) and float(rate) >= 1.0:
            reasons.append("EXTREME_ANNUAL_RATE_REVIEW")
        if reasons:
            exception_rows.append({
                "canonical_tcgplayer_product_id": row.get("canonical_tcgplayer_product_id"),
                "product_name": row.get("product_name"),
                "forecast_method_route": row.get("forecast_method_route"),
                "candidate_v2_3_base_annual_rate": row.get("candidate_v2_3_base_annual_rate"),
                "candidate_v2_3_confidence_score_0_to_100": row.get("candidate_v2_3_confidence_score_0_to_100"),
                "exception_reasons": "|".join(reasons),
                "production_eligible": False,
            })

    failures: list[str] = []
    if len(forecasts) != expectations["product_count"]:
        failures.append("product_count_mismatch")
    if int(complete.sum()) != expectations["complete_count"]:
        failures.append("complete_count_mismatch")
    if int(forecasts["forecast_method_route"].nunique()) != expectations["route_count"]:
        failures.append("route_count_mismatch")
    if int(reverse.sum()) != expectations["reverse_score_diagnostic_only_count"]:
        failures.append("reverse_score_count_mismatch")
    if int(hybrid.sum()) != expectations["japanese_hybrid_inactive_count"]:
        failures.append("hybrid_inactive_count_mismatch")
    if bool((downside.dropna() < expectations["maximum_downside_loss_floor"]).any()):
        failures.append("downside_loss_floor_violation")
    if bool((confidence[reverse].dropna() > expectations["maximum_reverse_score_confidence"]).any()):
        failures.append("reverse_confidence_ceiling_violation")
    if bool((confidence[hybrid].dropna() > expectations["maximum_inactive_hybrid_confidence"]).any()):
        failures.append("hybrid_confidence_ceiling_violation")

    authorization_columns = [
        "candidate_projection_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
    ]
    for column in authorization_columns:
        if column in forecasts.columns and bool(forecasts[column].map(truthy).any()):
            failures.append(f"authorization_open:{column}")

    hashes = pd.DataFrame([
        {"artifact_role": "candidate_forecasts", "path": str(forecasts_path.relative_to(ROOT)), "sha256": sha256_file(forecasts_path)},
        {"artifact_role": "candidate_summary", "path": str(summary_path.relative_to(ROOT)), "sha256": sha256_file(summary_path)},
        {"artifact_role": "candidate_approval", "path": str(approval_path.relative_to(ROOT)), "sha256": sha256_file(approval_path)},
        {"artifact_role": "candidate_builder", "path": str(builder_path.relative_to(ROOT)), "sha256": sha256_file(builder_path)},
        {"artifact_role": "candidate_audit", "path": str(audit_path.relative_to(ROOT)), "sha256": sha256_file(audit_path)},
    ])

    route = forecasts.groupby("forecast_method_route", dropna=False).agg(
        product_count=("canonical_tcgplayer_product_id", "count"),
        complete_count=("candidate_v2_3_calculation_complete", lambda s: int(s.map(truthy).sum())),
        mean_base_rate=("candidate_v2_3_base_annual_rate", "mean"),
        mean_scenario_width=("candidate_v2_3_scenario_width_final", "mean"),
        minimum_downside_rate=("candidate_v2_3_downside_annual_rate", "min"),
        maximum_upside_rate=("candidate_v2_3_upside_annual_rate", "max"),
        mean_confidence_0_to_100=("candidate_v2_3_confidence_score_0_to_100", "mean"),
    ).reset_index()

    freeze_status = "TECHNICAL_FREEZE_RECOMMENDED_WITH_EXCLUSIONS" if not failures else "TECHNICAL_FREEZE_NOT_RECOMMENDED"
    out = ROOT / cfg["output_directory"]
    out.mkdir(parents=True, exist_ok=True)
    hashes.to_csv(out / "collector_candidate_v2_3_artifact_hash_manifest.csv", index=False)
    route.to_csv(out / "collector_candidate_v2_3_final_route_validation.csv", index=False)
    pd.DataFrame(exception_rows).to_csv(out / "collector_candidate_v2_3_exception_register.csv", index=False)

    recommendation = {
        "review_name": cfg["review_name"],
        "review_version": cfg["review_version"],
        "freeze_recommendation": freeze_status,
        "candidate_version": "2.3.0",
        "candidate_summary_status": candidate_summary.get("status"),
        "technical_candidate_complete_count": int(complete.sum()),
        "documented_exclusions": cfg["freeze_policy"]["required_exclusions"],
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "reverse_score_production_use_authorized": False,
        "japanese_hybrid_formula_authorized": False,
        "prospective_accuracy_certified": False,
        "owner_freeze_approval_required": True,
    }
    (out / "collector_candidate_v2_3_freeze_recommendation.json").write_text(json.dumps(recommendation, indent=2, sort_keys=True), encoding="utf-8")

    summary = {
        "audit_name": cfg["review_name"],
        "audit_version": cfg["review_version"],
        "status": "PASS" if not failures else "FAIL",
        "freeze_recommendation": freeze_status,
        "product_count": int(len(forecasts)),
        "complete_count": int(complete.sum()),
        "route_count": int(forecasts["forecast_method_route"].nunique()),
        "reverse_score_diagnostic_only_count": int(reverse.sum()),
        "japanese_hybrid_inactive_count": int(hybrid.sum()),
        "exception_product_count": int(len(exception_rows)),
        "artifact_hash_count": int(len(hashes)),
        "minimum_downside_rate": None if downside.dropna().empty else float(downside.min()),
        "maximum_confidence_0_to_100": None if confidence.dropna().empty else float(confidence.max()),
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "owner_freeze_approval_required": True,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This review may recommend freezing Candidate v2.3 as the technical Collector forecast candidate with explicit exclusions. It does not authorize production forecasts, purchases, reverse-score production use, the Japanese hybrid formula, or accuracy certification.",
    }
    (out / "collector_candidate_v2_3_final_validation_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
