"""Audit Collector eBay acquisition recall using current and historical local evidence.

Offline-only. This block does not call eBay. It compares the current matching-validation
sample with prior Phase 10 listing artifacts, creates multi-query governed contracts,
and selects representative products for a later live high-recall canary.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
CURRENT_SHADOW = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection/collector_ebay_listing_observations_shadow.csv"
CURRENT_CONTRACTS = ROOT / "data/governance/permanence/certification/collector_ebay_supply_contracts/collector_ebay_search_contracts.csv"
HISTORICAL_ROOT = ROOT / "data"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_acquisition_recall"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline Collector eBay acquisition recall audit")
    p.add_argument("--authority", type=Path, default=AUTHORITY)
    p.add_argument("--current-shadow", type=Path, default=CURRENT_SHADOW)
    p.add_argument("--current-contracts", type=Path, default=CURRENT_CONTRACTS)
    p.add_argument("--historical-root", type=Path, default=HISTORICAL_ROOT)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--strict", action="store_true")
    return p


def norm_id(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def clean_name(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def normalize_title(value: object) -> str:
    text = clean_name(value).lower().replace("’", "'")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def first_present(frame: pd.DataFrame, names: Iterable[str]) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def discover_historical_files(root: Path, excluded: set[Path]) -> list[Path]:
    patterns = (
        "*ebay*listing*match*.csv",
        "*ebay*reclassified*.csv",
        "*ebay*consolidated*.csv",
        "*ebay*coverage*.csv",
        "*collector*ebay*batch*.csv",
    )
    found: set[Path] = set()
    for pattern in patterns:
        for path in root.rglob(pattern):
            resolved = path.resolve()
            if resolved not in excluded and path.is_file():
                found.add(resolved)
    return sorted(found)


def historical_rows(paths: list[Path], governed_ids: set[str]) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    inventory: list[dict[str, object]] = []
    for path in paths:
        try:
            frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        except Exception as exc:
            inventory.append({"path": str(path.relative_to(ROOT)), "read_status": "ERROR", "rows": 0, "error": f"{type(exc).__name__}: {exc}"})
            continue
        pid_col = first_present(frame, ["tcgplayer_product_id", "product_id", "target_tcgplayer_product_id"])
        item_col = first_present(frame, ["ebay_item_id", "item_id", "itemId"])
        title_col = first_present(frame, ["title", "listing_title", "raw_title", "title_production"])
        decision_col = first_present(frame, ["production_decision", "match_state", "listing_decision", "decision"])
        inventory.append({
            "path": str(path.relative_to(ROOT)),
            "read_status": "READ",
            "rows": len(frame),
            "pid_column": pid_col or "",
            "item_column": item_col or "",
            "title_column": title_col or "",
            "decision_column": decision_col or "",
        })
        if not pid_col or not item_col:
            continue
        for _, row in frame.iterrows():
            pid = norm_id(row.get(pid_col, ""))
            item_id = clean_name(row.get(item_col, ""))
            if pid not in governed_ids or not item_id:
                continue
            rows.append({
                "tcgplayer_product_id": pid,
                "ebay_item_id": item_id,
                "title": clean_name(row.get(title_col, "")) if title_col else "",
                "title_normalized": normalize_title(row.get(title_col, "")) if title_col else "",
                "decision": clean_name(row.get(decision_col, "")) if decision_col else "",
                "source_path": str(path.relative_to(ROOT)),
            })
    history = pd.DataFrame(rows)
    if not history.empty:
        history = history.drop_duplicates(["tcgplayer_product_id", "ebay_item_id", "source_path"])
    return history, inventory


def query_variants(name: str) -> list[tuple[str, str]]:
    base = re.sub(r"\s+Collector Booster Display$", "", name, flags=re.I).strip()
    aliases = {base, base.replace(":", " "), base.replace("'", ""), base.replace("Universes Beyond: ", "")}
    aliases = {" ".join(a.split()) for a in aliases if a.strip()}
    variants: list[tuple[str, str]] = []
    seen: set[str] = set()
    templates = (
        ("EXACT_MAGIC_BOX", '"{alias}" "Collector Booster Box" Magic sealed'),
        ("MTG_BOX", 'MTG "{alias}" "Collector Booster Box" sealed'),
        ("DISPLAY", '"{alias}" "Collector Booster Display" sealed'),
        ("BROAD_BOX", '"{alias}" collector booster box'),
        ("MAGIC_DISPLAY", 'Magic The Gathering "{alias}" collector booster display'),
    )
    for alias in sorted(aliases, key=len, reverse=True):
        for code, template in templates:
            query = template.format(alias=alias)
            key = query.lower()
            if key not in seen:
                seen.add(key)
                variants.append((code, query))
    return variants


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    required = [args.authority.resolve(), args.current_shadow.resolve()]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        summary = {"block_name": "Collector eBay Acquisition Recall Audit", "generated_at": generated.isoformat(), "missing_required_inputs": missing, "status": "REQUIRED_INPUTS_MISSING"}
        (out / "collector_ebay_acquisition_recall_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    authority = pd.read_csv(args.authority.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    shadow = pd.read_csv(args.current_shadow.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)
    shadow["tcgplayer_product_id"] = shadow["tcgplayer_product_id"].map(norm_id)
    governed_ids = set(authority["tcgplayer_product_id"])

    excluded = {args.current_shadow.resolve()}
    historical_paths = discover_historical_files(args.historical_root.resolve(), excluded)
    history, inventory = historical_rows(historical_paths, governed_ids)
    pd.DataFrame(inventory).to_csv(out / "collector_ebay_historical_evidence_inventory.csv", index=False)
    history.to_csv(out / "collector_ebay_historical_listing_evidence.csv", index=False)

    current_item_col = first_present(shadow, ["item_id", "ebay_item_id", "itemId"])
    if not current_item_col:
        raise SystemExit("Current shadow file has no eBay item ID column")
    current = shadow[["tcgplayer_product_id", current_item_col]].copy()
    current.columns = ["tcgplayer_product_id", "ebay_item_id"]
    current["ebay_item_id"] = current["ebay_item_id"].astype(str)
    current = current[current["ebay_item_id"].str.strip() != ""].drop_duplicates()

    coverage_rows: list[dict[str, object]] = []
    for _, auth in authority.iterrows():
        pid = norm_id(auth["tcgplayer_product_id"])
        name = clean_name(auth.get("box_name", auth.get("governed_box_name", "")))
        current_ids = set(current.loc[current["tcgplayer_product_id"] == pid, "ebay_item_id"])
        if history.empty:
            historical_ids: set[str] = set()
            historical_titles: list[str] = []
        else:
            subset = history[history["tcgplayer_product_id"] == pid]
            historical_ids = set(subset["ebay_item_id"])
            historical_titles = sorted(set(t for t in subset["title_normalized"] if t))
        overlap = current_ids & historical_ids
        historical_only = historical_ids - current_ids
        current_only = current_ids - historical_ids
        coverage_rows.append({
            "tcgplayer_product_id": pid,
            "governed_box_name": name,
            "current_sample_unique_item_ids": len(current_ids),
            "historical_unique_item_ids": len(historical_ids),
            "overlap_item_ids": len(overlap),
            "historical_only_item_ids": len(historical_only),
            "current_only_item_ids": len(current_only),
            "recoverable_evidence_overlap_rate": round(len(overlap) / len(historical_ids), 6) if historical_ids else "",
            "historical_title_pattern_count": len(historical_titles),
            "current_zero_is_true_zero_authorized": False,
            "acquisition_recall_status": "RECALL_GAP_EVIDENCE" if historical_only else "NO_HISTORICAL_GAP_DETECTED_NOT_CERTIFIED",
        })
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(out / "collector_ebay_product_recall_evidence.csv", index=False)

    contracts: list[dict[str, object]] = []
    for _, auth in authority.iterrows():
        pid = norm_id(auth["tcgplayer_product_id"])
        name = clean_name(auth.get("box_name", auth.get("governed_box_name", "")))
        for sequence, (variant, query) in enumerate(query_variants(name), start=1):
            contracts.append({
                "tcgplayer_product_id": pid,
                "governed_box_name": name,
                "query_variant_id": f"{pid}-{sequence:02d}",
                "query_variant_type": variant,
                "search_query": query,
                "pagination_required": True,
                "deduplicate_by": "EBAY_ITEM_ID",
                "matching_authority": "precision-v3-universal",
                "contract_status": "CANDIDATE_RECALL_CONTRACT_OFFLINE_NOT_LIVE_CERTIFIED",
            })
    pd.DataFrame(contracts).to_csv(out / "collector_ebay_multi_query_recall_contracts.csv", index=False)

    canary_roles = [
        ("ZERO_CURRENT_WITH_HISTORY", coverage[(coverage["current_sample_unique_item_ids"] == 0) & (coverage["historical_unique_item_ids"] > 0)]),
        ("HIGH_HISTORICAL_GAP", coverage.sort_values("historical_only_item_ids", ascending=False)),
        ("HIGH_CURRENT_VOLUME", coverage.sort_values("current_sample_unique_item_ids", ascending=False)),
        ("LOW_CURRENT_NONZERO", coverage[coverage["current_sample_unique_item_ids"] > 0].sort_values("current_sample_unique_item_ids")),
    ]
    canaries: list[dict[str, object]] = []
    used: set[str] = set()
    for role, frame in canary_roles:
        for _, row in frame.iterrows():
            pid = norm_id(row["tcgplayer_product_id"])
            if pid not in used:
                used.add(pid)
                canaries.append({**row.to_dict(), "canary_role": role, "live_canary_authorized": True})
                break
    pd.DataFrame(canaries).to_csv(out / "collector_ebay_high_recall_canary_plan.csv", index=False)

    historical_unique = int(history["ebay_item_id"].nunique()) if not history.empty else 0
    products_with_gap = int((coverage["historical_only_item_ids"] > 0).sum())
    current_zero_products = int((coverage["current_sample_unique_item_ids"] == 0).sum())
    current_zero_with_history = int(((coverage["current_sample_unique_item_ids"] == 0) & (coverage["historical_unique_item_ids"] > 0)).sum())
    summary = {
        "block_name": "Collector eBay Acquisition Recall Audit",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "governed_products": len(authority),
        "current_sample_unique_item_ids": int(current["ebay_item_id"].nunique()),
        "historical_evidence_files_read": sum(1 for item in inventory if item.get("read_status") == "READ"),
        "historical_unique_item_ids": historical_unique,
        "products_with_historical_only_item_ids": products_with_gap,
        "current_zero_products": current_zero_products,
        "current_zero_products_with_historical_evidence": current_zero_with_history,
        "multi_query_contract_rows": len(contracts),
        "canary_products": len(canaries),
        "acquisition_recall_certified": False,
        "current_sample_supply_baseline_authorized": False,
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_OFFLINE_ACQUISITION_RECALL_AUDIT_RECALL_NOT_CERTIFIED",
    }
    (out / "collector_ebay_acquisition_recall_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
