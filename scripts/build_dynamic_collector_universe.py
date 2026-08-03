"""Discover the dynamic Collector Booster Display universe from the latest TCGCSV snapshot.

The script never auto-admits a newly discovered product. It compares the latest
catalog snapshot with the currently governed map and emits additive review
queues. Previously governed products that disappear are also surfaced rather
than silently removed.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_dynamic_universe_policy_v1.json"
DEFAULT_SNAPSHOT_ROOT = ROOT / "data/operations/mtg_source_discovery/tcgcsv_snapshots"
DEFAULT_GOVERNED_MAP = ROOT / "data/governance/permanence/certification/collector_current_authority/governed_collector_tcgcsv_product_map.csv"
DEFAULT_OUTPUT = ROOT / "data/governance/permanence/certification/collector_dynamic_universe"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build dynamic Collector universe from latest TCGCSV snapshot")
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    p.add_argument("--governed-map", type=Path, default=DEFAULT_GOVERNED_MAP)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--strict", action="store_true")
    return p


def clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_id(value: object) -> str:
    value = clean(value)
    return value[:-2] if value.endswith(".0") else value


def normalize_marker_text(value: object) -> str:
    """Normalize naming variants without changing the preserved source name.

    TCGCSV contains variants such as ``Master Case`` and ``MasterCase``. Marker
    matching therefore removes punctuation and whitespace after lowercasing so
    semantically identical configuration names classify the same way.
    """
    return re.sub(r"[^a-z0-9]+", "", clean(value).lower())


def pick_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {str(c).lower(): str(c) for c in frame.columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def latest_snapshot_products(snapshot_root: Path) -> tuple[Path | None, str]:
    runs = sorted([p for p in snapshot_root.glob("*") if p.is_dir()], reverse=True)
    for run in runs:
        candidate = run / "tcgcsv_magic_products.csv"
        if candidate.is_file():
            return candidate, run.name
    return None, ""


def contains_marker(name: str, markers: list[str]) -> str:
    normalized_name = normalize_marker_text(name)
    for marker in markers:
        normalized_marker = normalize_marker_text(marker)
        if normalized_marker and normalized_marker in normalized_name:
            return marker
    return ""


def main() -> int:
    args = parser().parse_args()
    policy_path = args.policy.resolve()
    snapshot_root = args.snapshot_root.resolve()
    governed_map_path = args.governed_map.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    if not policy_path.is_file():
        failures.append("dynamic_universe_policy_missing")
    if not governed_map_path.is_file():
        failures.append("governed_product_map_missing")

    snapshot_path, snapshot_run_id = latest_snapshot_products(snapshot_root)
    if snapshot_path is None:
        failures.append("tcgcsv_catalog_snapshot_missing")

    if failures:
        summary = {
            "block_name": "Dynamic Collector Universe Discovery",
            "block_version": "1.0.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "FAIL",
            "failures": failures,
            "historical_append_authorized": False,
            "forecasting_resume_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        (output_dir / "collector_dynamic_universe_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    products = pd.read_csv(snapshot_path, dtype=str).fillna("")
    governed = pd.read_csv(governed_map_path, dtype=str).fillna("")

    pid_col = pick_column(products, ["productId", "product_id", "tcgplayer_product_id"])
    name_col = pick_column(products, ["name", "product_name", "cleanName", "clean_name"])
    category_col = pick_column(products, ["categoryId", "category_id", "tcgcsv_category_id"])
    group_col = pick_column(products, ["groupId", "group_id", "tcgcsv_group_id"])
    url_col = pick_column(products, ["url", "product_url"])
    modified_col = pick_column(products, ["modifiedOn", "modified_on"])

    required_missing = [name for name, col in {
        "product_id": pid_col,
        "product_name": name_col,
        "category_id": category_col,
        "group_id": group_col,
    }.items() if col is None]
    if required_missing:
        failures.append("snapshot_schema_missing:" + ",".join(required_missing))
        summary = {
            "block_name": "Dynamic Collector Universe Discovery",
            "block_version": "1.0.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "FAIL",
            "snapshot_path": str(snapshot_path),
            "failures": failures,
            "historical_append_authorized": False,
            "forecasting_resume_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        (output_dir / "collector_dynamic_universe_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    candidate_markers = policy["discovery"]["candidate_name_markers"]
    excluded_markers = policy["discovery"]["excluded_name_markers"]
    foreign_markers = policy["discovery"]["foreign_language_markers"]

    catalog_rows: list[dict[str, object]] = []
    for _, row in products.iterrows():
        pid = norm_id(row[pid_col])
        name = clean(row[name_col])
        if not pid or not name:
            continue
        candidate_marker = contains_marker(name, candidate_markers)
        if not candidate_marker:
            continue
        excluded_marker = contains_marker(name, excluded_markers)
        foreign_marker = contains_marker(name, foreign_markers)
        if foreign_marker:
            state = "EXCLUDED_FOREIGN_LANGUAGE"
            reason = f"FOREIGN_LANGUAGE_MARKER:{foreign_marker}"
        elif excluded_marker:
            state = "EXCLUDED_CONFIGURATION"
            reason = f"EXCLUDED_CONFIGURATION_MARKER:{excluded_marker}"
        else:
            state = "DISCOVERED_CONFIGURATION_CANDIDATE"
            reason = f"CANDIDATE_MARKER:{candidate_marker}"
        catalog_rows.append({
            "tcgplayer_product_id": pid,
            "source_product_name": name,
            "tcgcsv_category_id": norm_id(row[category_col]),
            "tcgcsv_group_id": norm_id(row[group_col]),
            "source_url": clean(row[url_col]) if url_col else "",
            "source_modified_on": clean(row[modified_col]) if modified_col else "",
            "snapshot_run_id": snapshot_run_id,
            "snapshot_path": str(snapshot_path),
            "discovery_state": state,
            "discovery_reason": reason,
        })

    catalog = pd.DataFrame(catalog_rows)
    if catalog.empty:
        catalog = pd.DataFrame(columns=[
            "tcgplayer_product_id", "source_product_name", "tcgcsv_category_id",
            "tcgcsv_group_id", "source_url", "source_modified_on", "snapshot_run_id",
            "snapshot_path", "discovery_state", "discovery_reason"
        ])
    catalog = catalog.drop_duplicates("tcgplayer_product_id", keep="last")

    governed["tcgplayer_product_id"] = governed["tcgplayer_product_id"].map(norm_id)
    governed_ids = set(governed["tcgplayer_product_id"])
    catalog_ids = set(catalog["tcgplayer_product_id"])

    catalog["previously_governed"] = catalog["tcgplayer_product_id"].isin(governed_ids)
    catalog["universe_state"] = catalog.apply(
        lambda r: (
            "GOVERNED_ACTIVE"
            if bool(r["previously_governed"]) and r["discovery_state"] == "DISCOVERED_CONFIGURATION_CANDIDATE"
            else "NEW_CANDIDATE_REVIEW_REQUIRED"
            if not bool(r["previously_governed"]) and r["discovery_state"] == "DISCOVERED_CONFIGURATION_CANDIDATE"
            else r["discovery_state"]
        ), axis=1
    )

    missing_governed = governed.loc[~governed["tcgplayer_product_id"].isin(catalog_ids)].copy()
    if len(missing_governed):
        missing_governed["universe_state"] = "MISSING_FROM_LATEST_SNAPSHOT_REVIEW_REQUIRED"
        missing_governed["snapshot_run_id"] = snapshot_run_id
        missing_governed["snapshot_path"] = str(snapshot_path)

    active = catalog.loc[catalog["universe_state"].eq("GOVERNED_ACTIVE")].copy()
    new_candidates = catalog.loc[catalog["universe_state"].eq("NEW_CANDIDATE_REVIEW_REQUIRED")].copy()
    excluded = catalog.loc[catalog["universe_state"].isin(["EXCLUDED_CONFIGURATION", "EXCLUDED_FOREIGN_LANGUAGE"])].copy()

    catalog.to_csv(output_dir / "collector_dynamic_universe_all.csv", index=False)
    active.to_csv(output_dir / "collector_dynamic_governed_active.csv", index=False)
    new_candidates.to_csv(output_dir / "collector_dynamic_new_candidate_queue.csv", index=False)
    missing_governed.to_csv(output_dir / "collector_dynamic_missing_governed_review.csv", index=False)
    excluded.to_csv(output_dir / "collector_dynamic_excluded.csv", index=False)

    summary = {
        "block_name": "Dynamic Collector Universe Discovery",
        "block_version": "1.0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_run_id": snapshot_run_id,
        "snapshot_path": str(snapshot_path),
        "snapshot_product_rows": int(len(products)),
        "collector_named_rows": int(len(catalog)),
        "governed_map_rows": int(len(governed)),
        "governed_active_rows": int(len(active)),
        "new_candidate_review_rows": int(len(new_candidates)),
        "excluded_rows": int(len(excluded)),
        "missing_governed_review_rows": int(len(missing_governed)),
        "fixed_product_count_assumed": False,
        "automatic_new_product_admission": False,
        "marker_matching_normalized": True,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_DYNAMIC_DISCOVERY" if len(missing_governed) == 0 else "REVIEW_REQUIRED",
        "failures": [],
    }
    (output_dir / "collector_dynamic_universe_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if args.strict and (len(missing_governed) > 0 or len(new_candidates) > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
