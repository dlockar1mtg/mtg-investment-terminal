from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_premodel_governance_remediation_contract_v1.json"
PREMODEL = ROOT / "data/governance/permanence/certification/collector_v1_premodel_reasonableness_audit"
LEDGER_DIR = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger"
FOUNDATION = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation/collector_v1_august1_snapshot_bound_current_foundation.csv"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_premodel_governance_remediation"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def date_value(value: Any) -> datetime | None:
    text = clean(value)[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lifecycle_band(days: int, bands: dict[str, list[int]]) -> str:
    for name, bounds in bands.items():
        if int(bounds[0]) <= days <= int(bounds[1]):
            return name
    return "UNCLASSIFIED"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    required_paths = [ROOT / path for path in contract["required_artifacts"]]
    missing = [path for path in required_paths if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_ARTIFACTS:" + ";".join(str(p) for p in missing))

    product_path = PREMODEL / "collector_premodel_product_reasonableness.csv"
    anomaly_path = PREMODEL / "collector_premodel_anomalies.csv"
    risk_path = PREMODEL / "collector_premodel_structural_risks.csv"
    summary_path = PREMODEL / "collector_premodel_reasonableness_summary.json"
    ledger_path = LEDGER_DIR / "collector_august1_historical_observation_ledger.csv"
    ledger_summary_path = LEDGER_DIR / "collector_august1_historical_observation_ledger_summary.json"

    products = read_csv(product_path)
    anomalies = read_csv(anomaly_path)
    risks = read_csv(risk_path)
    ledger = read_csv(ledger_path)
    foundation = read_csv(FOUNDATION)
    premodel_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ledger_summary = json.loads(ledger_summary_path.read_text(encoding="utf-8"))

    if len(products) != contract["required_product_count"]:
        failures.append("PRODUCT_COUNT_MISMATCH")
    if len(foundation) != contract["required_product_count"]:
        failures.append("FOUNDATION_COUNT_MISMATCH")
    if len(ledger) != contract["required_ledger_rows"]:
        failures.append("LEDGER_ROW_COUNT_MISMATCH")
    if len(risks) != contract["required_risk_count"]:
        failures.append("RISK_COUNT_MISMATCH")
    if premodel_summary.get("status") != "PASS_COLLECTOR_PREMODEL_REASONABLENESS_AUDIT_COMPLETED":
        failures.append("PREMODEL_AUDIT_NOT_CERTIFIED")
    if ledger_summary.get("status") != "PASS_COLLECTOR_AUGUST1_HISTORICAL_OBSERVATION_LEDGER":
        failures.append("LEDGER_NOT_CERTIFIED")

    foundation_by_id = {clean(r.get("identity__canonical_product_id")): r for r in foundation}
    product_by_id = {clean(r.get("canonical_product_id")): r for r in products}

    artifact_rows: list[dict[str, Any]] = []
    for path in required_paths:
        artifact_rows.append({
            "artifact_path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "inventory_generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "inventory_status": "INCLUDED_CURRENT_RUN",
        })

    feature_rows = [
        {"feature_name": "selected_price", "feature_class": "HISTORICALLY_AVAILABLE", "backtest_allowed": True, "required_lag": 0, "notes": "Certified monthly historical price."},
        {"feature_name": "selection_method", "feature_class": "HISTORICALLY_AVAILABLE", "backtest_allowed": True, "required_lag": 0, "notes": "Use as methodology control, not a target-derived future feature."},
        {"feature_name": "historical_return", "feature_class": "DERIVED_FROM_HISTORICAL_LEDGER", "backtest_allowed": True, "required_lag": 1, "notes": "Must be calculated using observations available at the forecast cutoff."},
        {"feature_name": "rolling_volatility", "feature_class": "DERIVED_FROM_HISTORICAL_LEDGER", "backtest_allowed": True, "required_lag": 1, "notes": "Trailing-only calculation."},
        {"feature_name": "release_date", "feature_class": "STATIC_PRODUCT_ATTRIBUTE", "backtest_allowed": True, "required_lag": 0, "notes": "Official release authority."},
        {"feature_name": "licensed_ip_or_product_family", "feature_class": "STATIC_PRODUCT_ATTRIBUTE", "backtest_allowed": True, "required_lag": 0, "notes": "Allowed only when known at the forecast cutoff."},
        {"feature_name": "august1_current_price", "feature_class": "CURRENT_ONLY", "backtest_allowed": False, "required_lag": "N/A", "notes": "Forecast-origin anchor only; never historical backtest input."},
        {"feature_name": "ebay_listing_count", "feature_class": "PROHIBITED_FOR_BACKTEST", "backtest_allowed": False, "required_lag": "N/A", "notes": "Current-only supply evidence."},
        {"feature_name": "ebay_seller_count", "feature_class": "PROHIBITED_FOR_BACKTEST", "backtest_allowed": False, "required_lag": "N/A", "notes": "Current-only market depth evidence."},
        {"feature_name": "current_scarcity_tier", "feature_class": "PROHIBITED_FOR_BACKTEST", "backtest_allowed": False, "required_lag": "N/A", "notes": "Current-only ranking overlay."},
        {"feature_name": "current_eligibility_status", "feature_class": "PROHIBITED_FOR_BACKTEST", "backtest_allowed": False, "required_lag": "N/A", "notes": "Would leak the August 1 universe definition."},
        {"feature_name": "current_ranking_or_review_outcome", "feature_class": "PROHIBITED_FOR_BACKTEST", "backtest_allowed": False, "required_lag": "N/A", "notes": "Direct look-ahead leakage."},
    ]

    lifecycle_rows: list[dict[str, Any]] = []
    for row in ledger:
        canonical_id = clean(row.get("canonical_product_id"))
        foundation_row = foundation_by_id.get(canonical_id, {})
        release = date_value(foundation_row.get("identity__raw_released_on"))
        observation = date_value(row.get("observation_date"))
        if release is None or observation is None:
            failures.append(f"LIFECYCLE_DATE_MISSING:{canonical_id}")
            days = 0
            band = "UNCLASSIFIED"
        else:
            days = (observation - release).days
            band = lifecycle_band(days, contract["lifecycle_bands"])
        lifecycle_rows.append({
            "ledger_observation_id": clean(row.get("ledger_observation_id")),
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": clean(row.get("tcgplayer_product_id")),
            "product_name": clean(row.get("canonical_product_name")),
            "observation_date": clean(row.get("observation_date"))[:10],
            "release_date": release.date().isoformat() if release else "",
            "days_from_release": days,
            "lifecycle_band": band,
            "selected_price": clean(row.get("selected_price")),
            "selection_method": clean(row.get("selection_method")),
            "panel_status": "CANDIDATE_NOT_YET_AUTHORIZED",
        })

    anomaly_queue: list[dict[str, Any]] = []
    for index, row in enumerate(anomalies, start=1):
        anomaly_queue.append({
            "review_id": f"ANOM-{index:04d}",
            **row,
            "automated_disposition": "PENDING_EVIDENCE_REVIEW",
            "required_evidence": (
                "market_mid_low_high_nearby_months;method_consistency;post_event_persistence"
                if clean(row.get("anomaly_type")) == "EXTREME_MONTHLY_RETURN"
                else "lifecycle_or_method_transition_evidence"
            ),
            "human_disposition": "",
            "human_rationale": "",
            "modeling_use_until_resolved": "SENSITIVITY_ONLY",
        })

    comparable_queue: list[dict[str, Any]] = []
    authorization_rows: list[dict[str, Any]] = []
    anchor_rows: list[dict[str, Any]] = []
    for product in products:
        canonical_id = clean(product.get("canonical_product_id"))
        foundation_row = foundation_by_id.get(canonical_id, {})
        model_class = clean(product.get("modeling_classification"))
        current_price = number(product.get("current_price"))
        source_status = clean(product.get("current_price_authority_status"))
        anchor_valid = current_price is not None and current_price > 0
        anchor_status = (
            "TECHNICALLY_VALID_PENDING_STATUS_PROMOTION"
            if anchor_valid and source_status not in {"CURRENT_PRICE_AUTHORIZED", "CURRENT_PRICE_CERTIFIED"}
            else "FINAL_AUTHORITY_VALID" if anchor_valid else "BLOCKED_INVALID_CURRENT_PRICE"
        )
        anchor_rows.append({
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": clean(product.get("tcgplayer_product_id")),
            "product_name": clean(product.get("product_name")),
            "current_price": current_price if current_price is not None else "",
            "source_authority_status": source_status,
            "anchor_validation_status": anchor_status,
            "forecast_anchor_allowed": False,
            "required_action": "PROMOTE_OR_BLOCK_CURRENT_PRICE_AUTHORITY",
        })

        if model_class == "COMPARABLE_ROUTE_REVIEW_REQUIRED":
            comparable_queue.append({
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": clean(product.get("tcgplayer_product_id")),
                "product_name": clean(product.get("product_name")),
                "observation_count": clean(product.get("observation_count")),
                "forecast_route": clean(product.get("forecast_route")),
                "reported_comparable_rows": clean(product.get("comparable_rows")),
                "required_dimensions": "product_type;release_era;licensed_ip;set_category;box_configuration;price_tier;lifecycle_shape",
                "time_safe_cutoff_required": True,
                "review_status": "PENDING_COMPARABLE_POOL_CERTIFICATION",
                "modeling_authorized": False,
            })

        if model_class == "SIMPLE_MODEL_TOURNAMENT_CANDIDATE":
            proposed = "CONDITIONAL_SIMPLE_MODELS_ONLY"
        elif model_class == "LIMITED_MODEL_FAMILIES_ONLY":
            proposed = "CONDITIONAL_LIMITED_MODELS_ONLY"
        elif model_class == "COMPARABLE_ROUTE_REVIEW_REQUIRED":
            proposed = "BLOCKED_PENDING_COMPARABLE_CERTIFICATION"
        else:
            proposed = "BLOCKED_INSUFFICIENT_HISTORY"
        authorization_rows.append({
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": clean(product.get("tcgplayer_product_id")),
            "product_name": clean(product.get("product_name")),
            "premodel_classification": model_class,
            "proposed_modeling_status": proposed,
            "current_price_anchor_status": anchor_status,
            "anomaly_review_required": any(clean(a.get("canonical_product_id")) == canonical_id for a in anomalies),
            "comparable_review_required": model_class == "COMPARABLE_ROUTE_REVIEW_REQUIRED",
            "final_modeling_authorized": False,
            "blocking_reasons": "CURRENT_PRICE_STATUS_NOT_FINAL;FINAL_REMEDIATION_CERTIFICATION_NOT_COMPLETE",
        })

    unresolved_risks = [r for r in risks if clean(r.get("status")) in {"REVIEW_REQUIRED", "STRUCTURAL_RISK_PRESENT"}]
    nonfinal_anchors = [r for r in anchor_rows if r["anchor_validation_status"] != "FINAL_AUTHORITY_VALID"]
    unclassified_lifecycle = [r for r in lifecycle_rows if r["lifecycle_band"] == "UNCLASSIFIED"]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact_output = OUTPUT / "collector_dynamic_artifact_manifest.csv"
    feature_output = OUTPUT / "collector_feature_availability_registry.csv"
    lifecycle_output = OUTPUT / "collector_lifecycle_panel_candidate.csv"
    anomaly_output = OUTPUT / "collector_anomaly_adjudication_queue.csv"
    comparable_output = OUTPUT / "collector_comparable_certification_queue.csv"
    anchor_output = OUTPUT / "collector_current_price_anchor_review.csv"
    authorization_output = OUTPUT / "collector_product_modeling_authorization_candidate.csv"
    summary_output = OUTPUT / "collector_premodel_governance_remediation_summary.json"

    write_csv(artifact_output, artifact_rows, ["artifact_path", "sha256", "size_bytes", "modified_at_utc", "inventory_generated_at_utc", "inventory_status"])
    write_csv(feature_output, feature_rows, ["feature_name", "feature_class", "backtest_allowed", "required_lag", "notes"])
    write_csv(lifecycle_output, lifecycle_rows, ["ledger_observation_id", "canonical_product_id", "tcgplayer_product_id", "product_name", "observation_date", "release_date", "days_from_release", "lifecycle_band", "selected_price", "selection_method", "panel_status"])
    write_csv(anomaly_output, anomaly_queue, list(anomaly_queue[0].keys()) if anomaly_queue else ["review_id"])
    write_csv(comparable_output, comparable_queue, list(comparable_queue[0].keys()) if comparable_queue else ["canonical_product_id"])
    write_csv(anchor_output, anchor_rows, list(anchor_rows[0].keys()))
    write_csv(authorization_output, authorization_rows, list(authorization_rows[0].keys()))

    summary = {
        "block_name": "Collector Pre-Model Governance Remediation",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_snapshot_id": contract["governing_snapshot_id"],
        "artifact_manifest_rows": len(artifact_rows),
        "feature_registry_rows": len(feature_rows),
        "lifecycle_candidate_rows": len(lifecycle_rows),
        "anomaly_review_rows": len(anomaly_queue),
        "comparable_review_rows": len(comparable_queue),
        "current_price_anchor_rows": len(anchor_rows),
        "nonfinal_current_price_anchor_rows": len(nonfinal_anchors),
        "product_authorization_candidate_rows": len(authorization_rows),
        "unresolved_structural_risk_rows": len(unresolved_risks),
        "unclassified_lifecycle_rows": len(unclassified_lifecycle),
        "dynamic_artifact_manifest_completed": not failures,
        "feature_availability_registry_completed": not failures,
        "lifecycle_candidate_built": not failures and not unclassified_lifecycle,
        "anomaly_review_queue_completed": not failures,
        "comparable_review_queue_completed": not failures,
        "current_price_final_authority_certified": False,
        "final_product_modeling_authorization": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_PREMODEL_GOVERNANCE_REMEDIATION_PACKAGE_BUILT" if not failures else "FAIL_COLLECTOR_PREMODEL_GOVERNANCE_REMEDIATION_PACKAGE",
    }
    summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
