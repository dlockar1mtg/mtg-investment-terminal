from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_historical_source_scope_lineage_contract_v1.json"
ROW_VERIFICATION = ROOT / "data/governance/permanence/certification/collector_v1_historical_row_level_temporal_verification/collector_v1_historical_row_level_temporal_verification.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_historical_source_scope_lineage"

COLLECTOR_HINTS = (
    "collector_booster", "collector booster", "collector_booster_box",
    "collector_boosters", "collector_v1", "collector_history",
)
SECRET_LAIR_HINTS = ("secret_lair", "secret lair")
PRE_COLLECTOR_HINTS = ("pre_collector", "pre-collector")
COPY_HINTS = (
    "backup", "backups", "repair_input", "promotion_backups",
    "attempts", "migration_", "reclassified", "consolidated",
)
CURRENT_HINTS = (
    "current_market", "latest_current", "current_price", "prices_current",
    "current\\", "current/", "snapshot",
)
CANONICAL_PRIORITY = (
    "canonical", "governed_historical_observations", "daily_price_observations",
    "monthly_archive_observations", "historical_observation_ledger",
    "price_history", "release_date_authority", "registry_baseline",
)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def contains_any(value: str, hints: tuple[str, ...]) -> bool:
    low = value.lower().replace("/", "\\")
    return any(hint.lower().replace("/", "\\") in low for hint in hints)


def canonical_rank(path_text: str) -> tuple[int, int, str]:
    low = path_text.lower()
    copy_penalty = 1 if contains_any(low, COPY_HINTS) else 0
    priority = next((i for i, hint in enumerate(CANONICAL_PRIORITY) if hint in low), len(CANONICAL_PRIORITY))
    return copy_penalty, priority, low


def scope_state(path_text: str) -> tuple[str, str]:
    if contains_any(path_text, SECRET_LAIR_HINTS):
        return "OUT_OF_SCOPE_SECRET_LAIR", "secret_lair_source"
    if contains_any(path_text, PRE_COLLECTOR_HINTS):
        return "OUT_OF_SCOPE_PRE_COLLECTOR", "pre_collector_source"
    if contains_any(path_text, CURRENT_HINTS) and not contains_any(path_text, ("history", "historical", "archive")):
        return "CURRENT_ONLY_SNAPSHOT", "current_only_source"
    if contains_any(path_text, COLLECTOR_HINTS):
        return "COLLECTOR_BOUND", ""
    return "COLLECTOR_BINDING_UNVERIFIED", "collector_scope_not_proven"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8-sig"))
    verified = pd.read_csv(ROW_VERIFICATION, dtype=str).fillna("")
    eligible = verified[verified["row_level_replay_eligible"].str.lower().eq("true")].copy()

    records: list[dict] = []
    for row in eligible.to_dict(orient="records"):
        rel = row["source_path"]
        source = ROOT / rel
        source_hash = file_sha256(source) if source.is_file() else ""
        state, scope_reason = scope_state(rel)
        is_copy = contains_any(rel, COPY_HINTS)
        scope_ok = state == "COLLECTOR_BOUND"
        records.append({
            "source_path": rel,
            "source_sha256": source_hash,
            "feature_family": row.get("feature_family", ""),
            "row_count": row.get("row_count", ""),
            "distinct_product_count": row.get("distinct_product_count", ""),
            "minimum_observation_date": row.get("minimum_observation_date", ""),
            "maximum_observation_date": row.get("maximum_observation_date", ""),
            "collector_scope_state": state,
            "copy_or_migration_artifact": is_copy,
            "scope_eligible": scope_ok,
            "scope_exclusion_reason": scope_reason,
        })

    frame = pd.DataFrame(records)
    if frame.empty:
        frame = pd.DataFrame(columns=[
            "source_path", "source_sha256", "feature_family", "row_count",
            "distinct_product_count", "minimum_observation_date",
            "maximum_observation_date", "collector_scope_state",
            "copy_or_migration_artifact", "scope_eligible",
            "scope_exclusion_reason",
        ])

    family_map: dict[str, dict] = {}
    for source_hash, group in frame.groupby("source_sha256", dropna=False):
        paths = sorted(group["source_path"].tolist(), key=canonical_rank)
        canonical = paths[0] if paths else ""
        family_id = hashlib.sha256((source_hash or canonical).encode("utf-8")).hexdigest()[:16]
        family_map[source_hash] = {
            "lineage_family_id": family_id,
            "canonical_source_path": canonical,
            "duplicate_family_size": len(paths),
        }

    output_rows: list[dict] = []
    for row in frame.to_dict(orient="records"):
        family = family_map[row["source_sha256"]]
        canonical = row["source_path"] == family["canonical_source_path"]
        copy_artifact = bool(row["copy_or_migration_artifact"])
        lineage_ok = canonical and not copy_artifact
        panel_candidate = bool(row["scope_eligible"]) and lineage_ok
        reasons: list[str] = []
        if not row["scope_eligible"]:
            reasons.append(row["scope_exclusion_reason"] or "scope_ineligible")
        if copy_artifact:
            reasons.append("copy_or_migration_artifact")
        if not canonical:
            reasons.append("noncanonical_duplicate_family_member")
        output_rows.append({
            **row,
            **family,
            "canonical_representative": canonical,
            "lineage_eligible": lineage_ok,
            "panel_candidate": panel_candidate,
            "exclusion_reason": "|".join(dict.fromkeys(reasons)),
        })

    result = pd.DataFrame(output_rows)
    adjudication_path = OUT / "collector_v1_historical_source_scope_lineage_adjudication.csv"
    candidates_path = OUT / "collector_v1_historical_panel_source_candidates.csv"
    exclusions_path = OUT / "collector_v1_historical_source_scope_lineage_exclusions.csv"
    result.to_csv(adjudication_path, index=False)
    result[result["panel_candidate"].eq(True)].to_csv(candidates_path, index=False)
    result[result["panel_candidate"].ne(True)].to_csv(exclusions_path, index=False)

    checks = {
        "contract_present": CONTRACT.is_file(),
        "row_verification_present": ROW_VERIFICATION.is_file(),
        "all_row_level_candidates_adjudicated": len(result) == len(eligible),
        "required_output_fields_present": set(contract["required_output_fields"]).issubset(result.columns),
        "secret_lair_not_panel_candidate": not bool(result.loc[result["collector_scope_state"].eq("OUT_OF_SCOPE_SECRET_LAIR"), "panel_candidate"].any()),
        "pre_collector_not_panel_candidate": not bool(result.loc[result["collector_scope_state"].eq("OUT_OF_SCOPE_PRE_COLLECTOR"), "panel_candidate"].any()),
        "one_canonical_per_lineage_family": bool((result.groupby("lineage_family_id")["canonical_representative"].sum() == 1).all()) if not result.empty else False,
        "noncanonical_duplicates_not_panel_candidates": not bool(result.loc[result["canonical_representative"].ne(True), "panel_candidate"].any()),
        "panel_build_not_yet_authorized": contract["authorization"]["lifecycle_panel_build_authorized"] is False,
    }
    failures = [name for name, passed in checks.items() if not bool(passed)]
    panel_candidates = result[result["panel_candidate"].eq(True)]
    summary = {
        "block_name": "Collector V1 Historical Source Scope and Lineage Adjudication",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_level_candidate_source_count": len(eligible),
        "scope_lineage_adjudicated_source_count": len(result),
        "collector_bound_source_count": int(result["collector_scope_state"].eq("COLLECTOR_BOUND").sum()),
        "panel_candidate_source_count": len(panel_candidates),
        "excluded_source_count": int(result["panel_candidate"].ne(True).sum()),
        "duplicate_lineage_family_count": int((result.groupby("lineage_family_id").size() > 1).sum()),
        "scope_state_counts": result["collector_scope_state"].value_counts().sort_index().to_dict(),
        "panel_candidate_family_counts": panel_candidates["feature_family"].value_counts().sort_index().to_dict(),
        "adjudication_path": str(adjudication_path.relative_to(ROOT)),
        "adjudication_sha256": file_sha256(adjudication_path),
        "panel_candidates_path": str(candidates_path.relative_to(ROOT)),
        "panel_candidates_sha256": file_sha256(candidates_path),
        "exclusions_path": str(exclusions_path.relative_to(ROOT)),
        "exclusions_sha256": file_sha256(exclusions_path),
        "checks": checks,
        "critical_failures": failures,
        "source_scope_lineage_adjudication_certified": not failures,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "PASS_COLLECTOR_V1_HISTORICAL_SOURCE_SCOPE_LINEAGE_ADJUDICATION" if not failures else "FAIL_COLLECTOR_V1_HISTORICAL_SOURCE_SCOPE_LINEAGE_ADJUDICATION",
    }
    summary_path = OUT / "collector_v1_historical_source_scope_lineage_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
