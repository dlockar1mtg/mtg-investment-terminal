from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/validation/phase_10/collector_booster_boxes/governed_registry/collector_booster_box_governed_registry.csv"
MASTER = ROOT / "data/product_master/product_master_model_input.csv"
OUT = ROOT / "data/operations/collector_registry_reconciliation/candidate_v1_0_0"


def norm(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    text = re.sub(r"\bcollector booster (display|box)\b", "collector booster", text)
    return " ".join(text.split())


def clean_id(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def mode_or_default(df: pd.DataFrame, column: str, default: str) -> str:
    if column not in df.columns:
        return default
    values = df[column].dropna().astype(str).str.strip()
    values = values[~values.isin(["", "nan", "None"])]
    return values.mode().iloc[0] if not values.empty else default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    if not REGISTRY.exists():
        failures.append("governed_registry_missing")
    if not MASTER.exists():
        failures.append("product_master_missing")
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if args.strict else 0

    registry = pd.read_csv(REGISTRY, dtype=str, keep_default_na=False)
    master = pd.read_csv(MASTER, dtype=str, keep_default_na=False, low_memory=False)

    required_registry = {
        "canonical_product_id", "canonical_product_name", "normalized_product_name",
        "canonical_set_name", "product_class", "tcgplayer_product_id", "release_date",
        "ebay_query", "source_batch", "registry_status", "market_coverage_status",
    }
    required_master = {"tcgplayer_product_id", "box_name"}
    if not required_registry.issubset(registry.columns):
        failures.append("registry_schema_mismatch")
    if not required_master.issubset(master.columns):
        failures.append("master_schema_mismatch")
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if args.strict else 0

    registry["tcgplayer_product_id"] = registry["tcgplayer_product_id"].map(clean_id)
    master["tcgplayer_product_id"] = master["tcgplayer_product_id"].map(clean_id)

    collector_master = master.loc[
        master["box_name"].astype(str).str.contains("Collector Booster", case=False, na=False)
    ].copy()
    collector_master = collector_master.loc[collector_master["tcgplayer_product_id"].ne("")]
    collector_master = collector_master.drop_duplicates("tcgplayer_product_id", keep="last")

    master_ids = set(collector_master["tcgplayer_product_id"])
    registry_ids_before = set(registry["tcgplayer_product_id"])
    missing_ids = sorted(master_ids - registry_ids_before)
    registry_only_ids = sorted(registry_ids_before - master_ids)

    product_class = mode_or_default(registry, "product_class", "COLLECTOR_BOOSTER_BOX")
    registry_status = mode_or_default(registry, "registry_status", "ACTIVE")
    market_coverage_status = mode_or_default(registry, "market_coverage_status", "COVERED")
    batch = datetime.now(timezone.utc).strftime("DYNAMIC_REGISTRY_SYNC_%Y_%m_%d")
    additions: list[dict[str, str]] = []

    for tcg_id in missing_ids:
        row = collector_master.loc[collector_master["tcgplayer_product_id"] == tcg_id].iloc[0]
        name = str(row.get("box_name", "")).strip()
        if not name:
            failures.append(f"missing_box_name:{tcg_id}")
            continue
        release_date = str(row.get("published_on", "")).strip()[:10] or "NOT_AVAILABLE"
        set_name = re.sub(
            r"\s*-?\s*Collector Booster Display(?:\s*\([^)]*\))?$",
            "",
            name,
            flags=re.I,
        ).strip()
        additions.append({
            "canonical_product_id": tcg_id,
            "canonical_product_name": name,
            "normalized_product_name": norm(name),
            "canonical_set_name": set_name,
            "product_class": product_class,
            "tcgplayer_product_id": tcg_id,
            "release_date": release_date,
            "ebay_query": name,
            "source_batch": batch,
            "registry_status": registry_status,
            "market_coverage_status": market_coverage_status,
        })

    before_count = len(registry)
    if additions:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        registry.to_csv(
            OUT / f"collector_booster_box_governed_registry_before_sync_{timestamp}.csv",
            index=False,
        )
        registry = pd.concat([registry, pd.DataFrame(additions)], ignore_index=True)

    registry = registry.drop_duplicates("tcgplayer_product_id", keep="first")
    registry = registry.sort_values("canonical_product_name").reset_index(drop=True)
    registry.to_csv(REGISTRY, index=False)
    registry.to_csv(OUT / "collector_booster_box_governed_registry_reconciled.csv", index=False)
    pd.DataFrame(additions).to_csv(OUT / "collector_registry_reconciliation_additions.csv", index=False)

    registry_ids_after = set(registry["tcgplayer_product_id"].map(clean_id))
    missing_after = sorted(master_ids - registry_ids_after)
    if missing_after:
        failures.append("master_products_missing_after_sync:" + "|".join(missing_after))
    if registry["tcgplayer_product_id"].map(clean_id).duplicated().any():
        failures.append("duplicate_tcgplayer_ids")
    if registry["canonical_product_name"].duplicated().any():
        failures.append("duplicate_canonical_names")

    result = {
        "audit_name": "Collector Governed Registry Dynamic Sync",
        "audit_version": "2.0.0",
        "registry_count_before": int(before_count),
        "master_collector_count": int(len(master_ids)),
        "addition_count": int(len(additions)),
        "registry_count_after": int(len(registry)),
        "master_products_missing_after_sync": missing_after,
        "registry_only_product_count": int(len(registry_only_ids)),
        "registry_only_product_ids": registry_only_ids,
        "dynamic_count_policy": True,
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
    }
    (OUT / "collector_registry_reconciliation_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
