from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data/governance/permanence/certification/collector_v1_historical_source_scope_lineage/collector_v1_historical_panel_source_candidates.csv"
OUTDIR = ROOT / "data/governance/permanence/certification/collector_v1_historical_source_precedence"
REGISTRY = OUTDIR / "collector_v1_historical_source_precedence_registry.csv"
SUMMARY = OUTDIR / "collector_v1_historical_source_precedence_summary.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(path: str, family: str) -> tuple[str, int, str]:
    p = path.lower().replace("\\", "/")
    if "portfolio" in p or "owned_inventory" in p or "positions" in p:
        return "EXCLUDED_OPERATIONAL_OR_PORTFOLIO", 99, "portfolio_or_owned_state_not_market_history"
    if family == "product_identity":
        if "registry_baseline" in p or "universe_classification" in p:
            return "STATIC_IDENTITY_AUTHORITY", 1, "collector_identity_authority"
        return "FALLBACK_ONLY", 50, "secondary_identity_source"
    if "ebay_listing_match_results" in p:
        return "CORROBORATING_OBSERVATION", 20, "listing_level_asking_evidence_not_aggregated_price_authority"
    if "collector_booster_model_input" in p:
        return "FALLBACK_ONLY", 40, "derived_model_input_requires_raw_lineage_review"
    return "FALLBACK_ONLY", 50, "no_authoritative_raw_price_source_proven"


def main(strict: bool) -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    if not CANDIDATES.exists():
        raise FileNotFoundError(CANDIDATES)
    frame = pd.read_csv(CANDIDATES, dtype=str).fillna("")
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        role, rank, reason = classify(row["source_path"], row["feature_family"])
        rows.append({
            **row.to_dict(),
            "source_role": role,
            "precedence_rank": rank,
            "precedence_reason": reason,
            "usable_for_price_history": role == "AUTHORITATIVE_OBSERVATION",
            "usable_for_listing_corroboration": role == "CORROBORATING_OBSERVATION",
            "usable_for_identity": role == "STATIC_IDENTITY_AUTHORITY",
            "conflict_resolution_rule": "lowest_precedence_rank_wins_then_fail_closed_on_unresolved_value_conflict",
        })
    result = pd.DataFrame(rows).sort_values(["feature_family", "precedence_rank", "source_path"])
    result.to_csv(REGISTRY, index=False)
    role_counts = result["source_role"].value_counts().sort_index().to_dict()
    authoritative_price_count = int(((result["feature_family"] == "price") & (result["source_role"] == "AUTHORITATIVE_OBSERVATION")).sum())
    identity_authority_count = int((result["source_role"] == "STATIC_IDENTITY_AUTHORITY").sum())
    listing_corroboration_count = int((result["source_role"] == "CORROBORATING_OBSERVATION").sum())
    coverage_build_authorized = authoritative_price_count > 0 and identity_authority_count > 0
    summary = {
        "block_name": "Collector V1 Historical Source Precedence Registry",
        "block_version": "1.0.0",
        "candidate_source_count": int(len(result)),
        "source_role_counts": role_counts,
        "authoritative_price_source_count": authoritative_price_count,
        "identity_authority_source_count": identity_authority_count,
        "listing_corroboration_source_count": listing_corroboration_count,
        "registry_path": str(REGISTRY.relative_to(ROOT)),
        "registry_sha256": sha256(REGISTRY),
        "historical_coverage_assessment_authorized": coverage_build_authorized,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_V1_HISTORICAL_SOURCE_PRECEDENCE_REGISTRY" if len(result) > 0 else "FAIL_NO_SOURCE_CANDIDATES",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if strict and (len(result) == 0 or identity_authority_count == 0):
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    raise SystemExit(main(args.strict))
