"""Profile historical eBay result schemas for governed Collector recall recovery.

Offline-only. This script does not infer recall or call eBay. It inventories schema,
column values, sibling coverage files, and likely product-linkage strategies so the
historical listing evidence can be reconstructed without silently dropping files.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_historical_schema_recovery"

PRODUCT_HINTS = (
    "tcgplayer", "product", "target", "canonical", "universe", "sku", "set", "name"
)
ITEM_HINTS = ("ebay_item_id", "item_id", "itemid")
TITLE_HINTS = ("title", "listing_title", "raw_title")
DECISION_HINTS = ("decision", "match_state", "listing_decision", "production_decision")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Profile historical eBay schemas")
    p.add_argument("--data-root", type=Path, default=DATA)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--strict", action="store_true")
    return p


def discover(root: Path) -> list[Path]:
    patterns = (
        "*ebay_listing_match_results*.csv",
        "*ebay_offline_reclassified_listings*.csv",
        "*ebay_offline_changed_listings*.csv",
        "*ebay_consolidated*.csv",
    )
    found: set[Path] = set()
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path.is_file():
                found.add(path.resolve())
    return sorted(found)


def sample_values(frame: pd.DataFrame, column: str, limit: int = 8) -> str:
    values = []
    for value in frame[column].astype(str):
        text = value.strip()
        if text and text.lower() != "nan" and text not in values:
            values.append(text)
        if len(values) >= limit:
            break
    return json.dumps(values, ensure_ascii=False)


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    files = discover(args.data_root.resolve())
    file_rows: list[dict[str, object]] = []
    column_rows: list[dict[str, object]] = []
    schema_counts: Counter[str] = Counter()
    errors = 0

    for path in files:
        rel = str(path.relative_to(ROOT))
        try:
            frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        except Exception as exc:
            errors += 1
            file_rows.append({
                "path": rel,
                "read_status": "ERROR",
                "rows": 0,
                "columns": "",
                "schema_signature": "",
                "candidate_product_columns": "",
                "candidate_item_columns": "",
                "candidate_title_columns": "",
                "candidate_decision_columns": "",
                "sibling_coverage_exists": False,
                "reconstruction_strategy": "UNREADABLE",
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        columns = [str(c) for c in frame.columns]
        lower = {c: c.lower() for c in columns}
        product_cols = [c for c in columns if any(h in lower[c] for h in PRODUCT_HINTS)]
        item_cols = [c for c in columns if lower[c] in ITEM_HINTS or "item_id" in lower[c]]
        title_cols = [c for c in columns if any(h == lower[c] or h in lower[c] for h in TITLE_HINTS)]
        decision_cols = [c for c in columns if any(h in lower[c] for h in DECISION_HINTS)]
        signature = "|".join(columns)
        schema_counts[signature] += 1

        sibling = path.with_name(path.name.replace("ebay_listing_match_results", "ebay_product_coverage"))
        sibling_exists = sibling.is_file()
        explicit_pid = any("tcgplayer" in lower[c] and "product" in lower[c] for c in columns)
        named_product = any("canonical_product" in lower[c] or "matched_product" in lower[c] or "target_product" in lower[c] for c in columns)
        if explicit_pid:
            strategy = "DIRECT_TCGPLAYER_ID"
        elif named_product:
            strategy = "PRODUCT_NAME_TO_GOVERNED_AUTHORITY"
        elif sibling_exists:
            strategy = "BATCH_COVERAGE_PLUS_MATCH_METADATA"
        else:
            strategy = "TITLE_REPLAY_REQUIRED"

        file_rows.append({
            "path": rel,
            "read_status": "READ",
            "rows": len(frame),
            "columns": json.dumps(columns),
            "schema_signature": signature,
            "candidate_product_columns": json.dumps(product_cols),
            "candidate_item_columns": json.dumps(item_cols),
            "candidate_title_columns": json.dumps(title_cols),
            "candidate_decision_columns": json.dumps(decision_cols),
            "sibling_coverage_exists": sibling_exists,
            "sibling_coverage_path": str(sibling.relative_to(ROOT)) if sibling_exists else "",
            "reconstruction_strategy": strategy,
            "error": "",
        })

        for column in columns:
            column_rows.append({
                "path": rel,
                "column": column,
                "nonblank_rows": int((frame[column].astype(str).str.strip() != "").sum()),
                "unique_nonblank_values": int(frame.loc[frame[column].astype(str).str.strip() != "", column].nunique()),
                "sample_values_json": sample_values(frame, column),
                "product_linkage_candidate": any(h in column.lower() for h in PRODUCT_HINTS),
                "item_id_candidate": column.lower() in ITEM_HINTS or "item_id" in column.lower(),
                "title_candidate": "title" in column.lower(),
            })

    files_df = pd.DataFrame(file_rows)
    columns_df = pd.DataFrame(column_rows)
    files_df.to_csv(out / "collector_ebay_historical_schema_inventory.csv", index=False)
    columns_df.to_csv(out / "collector_ebay_historical_column_profiles.csv", index=False)

    strategy_counts = files_df[files_df.get("read_status", "") == "READ"]["reconstruction_strategy"].value_counts().to_dict() if not files_df.empty else {}
    summary = {
        "block_name": "Collector eBay Historical Schema Recovery",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "historical_result_files_discovered": len(files),
        "historical_result_files_read": int((files_df.get("read_status", "") == "READ").sum()) if not files_df.empty else 0,
        "historical_result_files_failed": errors,
        "distinct_schema_signatures": len(schema_counts),
        "reconstruction_strategy_counts": strategy_counts,
        "historical_recall_comparison_valid": False,
        "live_canary_authorized": False,
        "next_step": "Use schema profiles to reconstruct governed product linkage, rerun offline recall audit, then select canaries",
        "status": "PASS_HISTORICAL_SCHEMA_RECOVERY_PROFILE" if files and errors == 0 else "REVIEW_REQUIRED",
    }
    (out / "collector_ebay_historical_schema_recovery_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    passed = summary["status"].startswith("PASS_")
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
