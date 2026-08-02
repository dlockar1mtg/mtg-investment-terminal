"""Resolve the final Collector V1 canonical coherence exception without inventing data."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_governed_exception_resolution"
PATHS = {
    "canonical_routes": ROOT / "data/governance/permanence/certification/collector_v1_canonical_inputs/collector_v1_canonical_forecast_routes.csv",
    "canonical_history": ROOT / "data/governance/permanence/certification/collector_v1_canonical_inputs/collector_v1_canonical_daily_price_history.csv",
    "canonical_coherence": ROOT / "data/governance/permanence/certification/collector_v1_canonical_data_coherence/collector_v1_canonical_data_coherence_summary.json",
    "scarcity": ROOT / "data/governance/permanence/certification/collector_supply_scarcity_index_v1/collector_supply_scarcity_index_v1.csv",
    "release": ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv",
    "comparables": ROOT / "data/operations/collector_comparable_selection/candidate_v1_0_0/collector_selected_comparables.csv",
    "japanese_override": ROOT / "data/governance/mtg/collector_comparables/collector_japanese_edition_hybrid_override_v1.json",
}
EXPECTED_EXCEPTION_ID = "628315"
EXPECTED_ROUTE_METHOD = "FUNDAMENTAL_COMPARABLE_HYBRID"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def norm(value: object) -> str:
    text = str(value or "").strip().removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [name for name, path in PATHS.items() if not path.is_file()]
    if missing:
        summary = {
            "block_name": "Collector V1 Governed Exception Resolution",
            "block_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "missing_inputs": missing,
            "exception_resolution_certified": False,
            "status": "FAIL_REQUIRED_INPUTS_MISSING",
        }
        (OUT / "collector_v1_governed_exception_resolution_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    routes = pd.read_csv(PATHS["canonical_routes"], dtype=str, encoding="utf-8-sig").fillna("")
    history = pd.read_csv(PATHS["canonical_history"], dtype=str, encoding="utf-8-sig").fillna("")
    scarcity = pd.read_csv(PATHS["scarcity"], dtype=str, encoding="utf-8-sig").fillna("")
    release = pd.read_csv(PATHS["release"], dtype=str, encoding="utf-8-sig").fillna("")
    override_text = PATHS["japanese_override"].read_text(encoding="utf-8")
    coherence = json.loads(PATHS["canonical_coherence"].read_text(encoding="utf-8"))

    route_id_col = "tcgplayer_product_id"
    route_method_col = "forecast_method"
    route_name_col = "product_name"
    route_ids = set(routes[route_id_col].map(norm))
    scarcity_ids = set(scarcity["tcgplayer_product_id"].map(norm))
    release_ids = set(release["tcgplayer_product_id"].map(norm))
    history_ids = set(history["tcgplayer_product_id"].map(norm))

    routed_without_scarcity = sorted(route_ids - scarcity_ids)
    exception_rows = routes[routes[route_id_col].map(norm).eq(EXPECTED_EXCEPTION_ID)]
    exception_route = exception_rows.iloc[0].to_dict() if len(exception_rows) == 1 else {}
    method = str(exception_route.get(route_method_col, "")).strip()
    product_name = str(exception_route.get(route_name_col, "")).strip()
    investment_product_id = str(exception_route.get("investment_product_id", "")).strip()

    override_references_exception = (
        EXPECTED_EXCEPTION_ID in override_text
        or investment_product_id in override_text
    )
    only_expected_exception = routed_without_scarcity == [EXPECTED_EXCEPTION_ID]
    method_is_governed_hybrid = method == EXPECTED_ROUTE_METHOD
    history_absence_is_explicit = EXPECTED_EXCEPTION_ID not in history_ids
    release_absence_is_explicit = EXPECTED_EXCEPTION_ID not in release_ids
    scarcity_absence_is_explicit = EXPECTED_EXCEPTION_ID not in scarcity_ids
    prior_only_critical_failure_is_peer_evidence = (
        len(coherence.get("critical_failures", [])) == 1
        and coherence["critical_failures"][0].get("category") == "comparables"
        and EXPECTED_EXCEPTION_ID in coherence["critical_failures"][0].get("details", "")
    )

    checks = {
        "only_expected_routed_without_scarcity": only_expected_exception,
        "exception_route_is_unique": len(exception_rows) == 1,
        "exception_route_uses_governed_hybrid_method": method_is_governed_hybrid,
        "japanese_edition_override_references_exception": override_references_exception,
        "history_absence_is_explicit": history_absence_is_explicit,
        "release_absence_is_explicit": release_absence_is_explicit,
        "scarcity_absence_is_explicit": scarcity_absence_is_explicit,
        "prior_only_critical_failure_is_peer_evidence": prior_only_critical_failure_is_peer_evidence,
    }
    certified = all(checks.values())

    resolution_rows = [{
        "tcgplayer_product_id": EXPECTED_EXCEPTION_ID,
        "investment_product_id": investment_product_id,
        "product_name": product_name,
        "forecast_method": method,
        "exception_type": "JAPANESE_EDITION_HYBRID_OVERRIDE",
        "scarcity_v1_policy": "MISSING_NO_IMPUTATION_CONFIDENCE_PENALTY",
        "history_policy": "NO_DIRECT_HISTORY_USE_COMPARABLE_AND_FUNDAMENTAL_EVIDENCE",
        "release_policy": "USE_GOVERNED_OVERRIDE_AND_PRODUCT_MASTER_METADATA",
        "comparable_policy": "HYBRID_OVERRIDE_SATISFIES_PEER_EVIDENCE_GATE",
        "purchase_policy": "NO_PURCHASE_AUTHORIZATION_UNTIL MODEL_VALIDATION",
        "resolution_status": "CERTIFIED" if certified else "FAILED",
    }]
    pd.DataFrame(resolution_rows).to_csv(OUT / "collector_v1_governed_exception_resolution.csv", index=False)

    summary = {
        "block_name": "Collector V1 Governed Exception Resolution",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "exception_tcgplayer_product_id": EXPECTED_EXCEPTION_ID,
        "exception_product_name": product_name,
        "exception_forecast_method": method,
        "checks": checks,
        "exception_resolution_certified": certified,
        "seller_feature_disposition": "EXCLUDE_FROM_V1_DIFFERENTIATING_FEATURES_RETAIN_MISSINGNESS_FLAG",
        "feature_matrix_authorized": certified,
        "forecast_experiments_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "artifact_hashes": {name: sha256(path) for name, path in PATHS.items()},
        "status": "PASS_COLLECTOR_V1_GOVERNED_EXCEPTION_RESOLVED" if certified else "FAIL_COLLECTOR_V1_GOVERNED_EXCEPTION_UNRESOLVED",
    }
    (OUT / "collector_v1_governed_exception_resolution_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if certified else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
