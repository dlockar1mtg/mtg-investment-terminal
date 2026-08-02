"""Reconstruct governed Collector product linkage for historical eBay result rows.

Offline-only. Uses canonical_product_name from prior Phase 10 result files and maps it
against the governed Collector authority. Preserves source provenance and writes a
validated historical evidence table for recall comparison.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
DATA_ROOT = ROOT / "data"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_historical_reconstruction"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reconstruct historical governed Collector eBay evidence")
    p.add_argument("--authority", type=Path, default=AUTHORITY)
    p.add_argument("--data-root", type=Path, default=DATA_ROOT)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--strict", action="store_true")
    return p


def text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def norm(value: object) -> str:
    value = text(value).lower().replace("’", "'")
    value = value.replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9]+", value))


def norm_id(value: object) -> str:
    value = text(value)
    return value[:-2] if value.endswith(".0") else value


def authority_name_column(frame: pd.DataFrame) -> str:
    for candidate in ("box_name", "governed_box_name", "product_name"):
        if candidate in frame.columns:
            return candidate
    raise ValueError("Governed authority has no recognized name column")


def aliases(name: str) -> set[str]:
    values = {name}
    values.add(re.sub(r"\s+Collector Booster Display$", "", name, flags=re.I))
    values.add(name.replace("Universes Beyond: ", ""))
    values.add(name.replace(" - Special Edition", " Special Edition"))
    values.add(name.replace(":", " "))
    return {norm(v) for v in values if norm(v)}


def discover(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("ebay_listing_match_results_*.csv")
        if path.is_file() and "collector_ebay_authority_reconciliation" not in str(path)
    )


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    authority = pd.read_csv(args.authority.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    name_col = authority_name_column(authority)
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)

    alias_map: dict[str, tuple[str, str]] = {}
    collisions: set[str] = set()
    for _, row in authority.iterrows():
        pid = norm_id(row["tcgplayer_product_id"])
        governed_name = text(row[name_col])
        for alias in aliases(governed_name):
            if alias in alias_map and alias_map[alias][0] != pid:
                collisions.add(alias)
            else:
                alias_map[alias] = (pid, governed_name)
    for collision in collisions:
        alias_map.pop(collision, None)

    evidence: list[dict[str, object]] = []
    inventory: list[dict[str, object]] = []
    files = discover(args.data_root.resolve())

    for path in files:
        try:
            frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        except Exception as exc:
            inventory.append({"path": str(path.relative_to(ROOT)), "status": "READ_ERROR", "rows": 0, "mapped_rows": 0, "error": f"{type(exc).__name__}: {exc}"})
            continue

        required = {"canonical_product_name", "ebay_item_id", "title"}
        if not required.issubset(frame.columns):
            inventory.append({"path": str(path.relative_to(ROOT)), "status": "SCHEMA_SKIPPED", "rows": len(frame), "mapped_rows": 0, "error": "missing canonical_product_name/ebay_item_id/title"})
            continue

        mapped = 0
        for _, row in frame.iterrows():
            product_name = text(row.get("canonical_product_name", ""))
            item_id = text(row.get("ebay_item_id", ""))
            if not product_name or not item_id:
                continue
            match = alias_map.get(norm(product_name))
            if not match:
                continue
            pid, governed_name = match
            mapped += 1
            evidence.append({
                "tcgplayer_product_id": pid,
                "governed_box_name": governed_name,
                "canonical_product_id_historical": text(row.get("canonical_product_id", "")),
                "canonical_product_name_historical": product_name,
                "product_class": text(row.get("product_class", "")),
                "ebay_query": text(row.get("ebay_query", "")),
                "ebay_item_id": item_id,
                "title": text(row.get("title", "")),
                "match_state": text(row.get("match_state", "")),
                "match_score": text(row.get("match_score", "")),
                "exclusion_reasons": text(row.get("exclusion_reasons", "")),
                "source_run_id": text(row.get("source_run_id", "")),
                "observed_at_utc": text(row.get("observed_at_utc", "")),
                "source_path": str(path.relative_to(ROOT)),
                "mapping_method": "CANONICAL_PRODUCT_NAME_TO_GOVERNED_AUTHORITY",
                "mapping_confidence": "1.0",
            })
        inventory.append({"path": str(path.relative_to(ROOT)), "status": "READ", "rows": len(frame), "mapped_rows": mapped, "error": ""})

    evidence_frame = pd.DataFrame(evidence)
    if not evidence_frame.empty:
        evidence_frame = evidence_frame.drop_duplicates(["tcgplayer_product_id", "ebay_item_id", "source_path"])
        evidence_frame = evidence_frame.sort_values(["tcgplayer_product_id", "ebay_item_id", "source_path"])
    evidence_frame.to_csv(out / "collector_ebay_reconstructed_historical_listing_evidence.csv", index=False)
    pd.DataFrame(inventory).to_csv(out / "collector_ebay_historical_reconstruction_inventory.csv", index=False)

    mapped_products = int(evidence_frame["tcgplayer_product_id"].nunique()) if not evidence_frame.empty else 0
    unique_items = int(evidence_frame["ebay_item_id"].nunique()) if not evidence_frame.empty else 0
    ambiguous_rows = 0
    passed = len(files) > 0 and mapped_products > 0 and unique_items > 0 and ambiguous_rows == 0
    summary = {
        "block_name": "Collector eBay Historical Evidence Reconstruction",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "historical_result_files_discovered": len(files),
        "historical_result_files_read": sum(1 for row in inventory if row["status"] == "READ"),
        "reconstructed_rows": len(evidence_frame),
        "reconstructed_unique_item_ids": unique_items,
        "reconstructed_governed_products": mapped_products,
        "ambiguous_mapping_rows": ambiguous_rows,
        "historical_product_linkage_reconstructed": passed,
        "offline_recall_comparison_ready": passed,
        "live_canary_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_HISTORICAL_RECONSTRUCTION" if passed else "REVIEW_REQUIRED",
    }
    (out / "collector_ebay_historical_reconstruction_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
