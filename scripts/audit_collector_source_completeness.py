"""Audit Collector source completeness, availability, freshness, and permanence."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_source_completeness_policy_v1.json"
DEFAULT_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
DEFAULT_TIERS = ROOT / "data/governance/permanence/certification/collector_history_adjudication_tiering/collector_product_history_tiers.csv"
DEFAULT_HISTORY = ROOT / "data/governance/permanence/certification/collector_historical_bridge_certification/collector_bridged_analytical_history_candidate.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_source_completeness"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Audit Collector source completeness")
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument("--tiers", type=Path, default=DEFAULT_TIERS)
    p.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")


def choose(frame: pd.DataFrame, candidates: list[str]) -> str:
    return next((name for name in candidates if name in frame.columns), "")


def norm_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    required_inputs = [args.policy, args.authority, args.tiers, args.history]
    missing_inputs = [str(p) for p in required_inputs if not p.resolve().is_file()]
    if missing_inputs:
        summary = {"status": "FAIL", "missing_inputs": missing_inputs, "source_layer_certified": False}
        (out / "collector_source_completeness_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    policy = json.loads(args.policy.resolve().read_text(encoding="utf-8-sig"))
    authority = read_csv(args.authority.resolve())
    tiers = read_csv(args.tiers.resolve())
    history = read_csv(args.history.resolve())
    for frame in (authority, tiers, history):
        frame["tcgplayer_product_id"] = frame["tcgplayer_product_id"].map(norm_id)

    field_aliases = {
        "tcgplayer_product_id": ["tcgplayer_product_id"],
        "box_name": ["box_name", "box_name_current", "governed_box_name"],
        "identity_authority_status": ["identity_authority_status", "identity_authority_status_current"],
        "language_evidence": [
            "language_evidence", "language_evidence_current", "language_evidence_source",
            "language_authority_evidence", "language_status", "language_certification_status",
        ],
        "configuration_status": ["configuration_status", "configuration_status_current", "price_selection_status"],
        "release_date": ["release_date", "official_release_date"],
        "release_date_authority_status": ["release_date_authority_status", "release_date_verification_status"],
        "release_date_source_url": ["release_date_source_url", "source_url"],
        "market_price": ["market_price", "market_price_current"],
    }

    completeness_rows, missing_rows = [], []
    product_name_col = choose(authority, field_aliases["box_name"])
    for _, row in authority.iterrows():
        product_id = norm_id(row.get("tcgplayer_product_id", ""))
        product_name = str(row.get(product_name_col, "")).strip() if product_name_col else ""
        record = {"tcgplayer_product_id": product_id, "box_name": product_name}
        critical_complete = True
        for canonical in policy["critical_product_fields"]:
            source_col = choose(authority, field_aliases.get(canonical, [canonical]))
            value = str(row.get(source_col, "")).strip() if source_col else ""
            record[f"{canonical}_source_column"] = source_col
            record[f"{canonical}_status"] = "PRESENT" if value else "MISSING"
            if not value:
                critical_complete = False
                missing_rows.append({"tcgplayer_product_id": product_id, "box_name": product_name, "field": canonical,
                                     "source_column": source_col, "missingness_reason": "SOURCE_FIELD_BLANK_OR_ABSENT", "blocking": True})
        record["critical_source_complete"] = critical_complete
        completeness_rows.append(record)

    completeness = pd.DataFrame(completeness_rows)
    missingness = pd.DataFrame(missing_rows, columns=["tcgplayer_product_id", "box_name", "field", "source_column", "missingness_reason", "blocking"])

    source_registry_rows = []
    stale_required_sources = missing_required_sources = 0
    for source in policy["required_source_artifacts"]:
        artifact = ROOT / source["artifact"]
        exists = artifact.is_file(); age_hours = ""; freshness = "MISSING"
        if exists:
            age = max(0.0, (now.timestamp() - artifact.stat().st_mtime) / 3600.0)
            age_hours = round(age, 3); freshness = "FRESH" if age <= float(source["maximum_age_hours"]) else "STALE"
        required = bool(source["required"])
        missing_required_sources += int(required and not exists)
        stale_required_sources += int(required and freshness == "STALE")
        source_registry_rows.append({**source, "artifact_exists": exists, "artifact_age_hours": age_hours,
                                     "freshness_status": freshness, "blocking": required and freshness != "FRESH"})
    source_registry = pd.DataFrame(source_registry_rows)

    supply_demand = pd.DataFrame(policy["supply_demand_metrics"])
    supply_demand["model_use_status"] = supply_demand["availability"].map({
        "DIRECTLY_OBSERVED": "ALLOWED_AS_OBSERVED_INPUT", "DERIVED_PROXY": "ALLOWED_ONLY_WITH_PROXY_SUFFIX",
        "NOT_YET_CERTIFIED": "BLOCKED_PENDING_SOURCE_CERTIFICATION", "NOT_AVAILABLE_FROM_CURRENT_SOURCES": "EXPLICITLY_UNAVAILABLE",
        "NOT_PUBLICLY_DISCLOSED": "EXPLICITLY_UNAVAILABLE",
    }).fillna("REVIEW_REQUIRED")
    unavailable = supply_demand.loc[supply_demand["availability"].isin(["NOT_AVAILABLE_FROM_CURRENT_SOURCES", "NOT_PUBLICLY_DISCLOSED"])].copy()

    dependency_graph = {"graph_name": "Collector Source Pipeline Dependency Graph", "graph_version": "1.1.0",
                        "generated_at": now.isoformat(), "edges": [{"upstream": a, "downstream": b} for a, b in policy["pipeline_dependencies"]],
                        "fail_closed": True, "forecasting_resume_authorized": False, "purchase_recommendation_authorized": False,
                        "uip_delivery_authorized": False}

    duplicate_history_keys = int(history.duplicated(["tcgplayer_product_id", "observation_month"]).sum())
    released_without_history = int(((pd.to_numeric(tiers["released_history_months"], errors="coerce").fillna(0) == 0)
                                    & ~tiers["recomputed_lifecycle_state"].eq("PRESALE")).sum())
    unverified_lifecycle = int(tiers["recomputed_lifecycle_state"].eq("RELEASE_DATE_UNVERIFIED").sum())
    unknown_missingness_reasons = int((missingness["missingness_reason"].astype(str).str.strip() == "").sum()) if len(missingness) else 0
    critical_missing_fields = int(len(missingness))
    mtgjson_path = ROOT / "data/governance/permanence/certification/collector_mtgjson_sealed_crosswalk/collector_mtgjson_sealed_crosswalk.csv"
    supply_path = ROOT / "data/governance/permanence/certification/collector_supply_demand/collector_certified_listing_supply_snapshot.csv"
    mtgjson_crosswalk_missing = int(not mtgjson_path.is_file())
    listing_supply_not_certified = int(not supply_path.is_file())
    source_layer_blockers = critical_missing_fields + duplicate_history_keys + released_without_history + unverified_lifecycle + unknown_missingness_reasons + missing_required_sources + stale_required_sources

    completeness.to_csv(out / "collector_source_completeness_matrix.csv", index=False)
    missingness.to_csv(out / "collector_required_field_missingness.csv", index=False)
    source_registry.to_csv(out / "collector_source_registry.csv", index=False)
    supply_demand.to_csv(out / "collector_supply_demand_availability.csv", index=False)
    unavailable.to_csv(out / "collector_unavailable_metrics_registry.csv", index=False)
    (out / "collector_source_freshness_policy.json").write_text(json.dumps({"generated_at": now.isoformat(), "sources": policy["required_source_artifacts"]}, indent=2) + "\n", encoding="utf-8")
    (out / "collector_pipeline_dependency_graph.json").write_text(json.dumps(dependency_graph, indent=2) + "\n", encoding="utf-8")

    summary = {"block_name": "Collector Source Completeness and Permanence Audit", "block_version": "1.1.0", "generated_at": now.isoformat(),
               "governed_products": int(len(authority)), "critical_missing_fields": critical_missing_fields,
               "products_with_complete_critical_source_data": int(completeness["critical_source_complete"].sum()) if len(completeness) else 0,
               "duplicate_historical_product_month_keys": duplicate_history_keys, "released_products_without_history": released_without_history,
               "release_date_unverified_products": unverified_lifecycle, "unknown_missingness_reasons": unknown_missingness_reasons,
               "missing_required_source_artifacts": missing_required_sources, "stale_required_source_artifacts": stale_required_sources,
               "mtgjson_sealed_crosswalk_missing": mtgjson_crosswalk_missing, "listing_supply_snapshot_not_certified": listing_supply_not_certified,
               "directly_observed_supply_demand_metrics": int(supply_demand["availability"].eq("DIRECTLY_OBSERVED").sum()),
               "derived_proxy_metrics": int(supply_demand["availability"].eq("DERIVED_PROXY").sum()),
               "not_yet_certified_metrics": int(supply_demand["availability"].eq("NOT_YET_CERTIFIED").sum()),
               "explicitly_unavailable_metrics": int(supply_demand["availability"].isin(["NOT_AVAILABLE_FROM_CURRENT_SOURCES", "NOT_PUBLICLY_DISCLOSED"]).sum()),
               "source_layer_blockers": int(source_layer_blockers), "source_layer_certified": source_layer_blockers == 0,
               "forecasting_resume_authorized": False, "purchase_recommendation_authorized": False, "uip_delivery_authorized": False,
               "status": "PASS_SOURCE_COMPLETENESS_FOUNDATION" if source_layer_blockers == 0 else "REVIEW_REQUIRED"}
    (out / "collector_source_completeness_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and source_layer_blockers > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
