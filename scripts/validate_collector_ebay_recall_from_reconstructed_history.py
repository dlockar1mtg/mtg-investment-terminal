"""Compare the current Collector eBay sample with reconstructed governed history."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
CURRENT = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection/collector_ebay_listing_observations_shadow.csv"
HISTORY = ROOT / "data/governance/permanence/certification/collector_ebay_historical_reconstruction/collector_ebay_reconstructed_historical_listing_evidence.csv"
CONTRACTS = ROOT / "data/governance/permanence/certification/collector_ebay_acquisition_recall/collector_ebay_multi_query_recall_contracts.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_reconstructed_recall"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate Collector eBay recall from reconstructed history")
    p.add_argument("--strict", action="store_true")
    return p


def norm_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    missing = [str(path) for path in (AUTHORITY, CURRENT, HISTORY, CONTRACTS) if not path.is_file()]
    if missing:
        summary = {"block_name": "Collector eBay Reconstructed Recall Validation", "generated_at": generated.isoformat(), "missing_inputs": missing, "status": "REQUIRED_INPUTS_MISSING"}
        (OUT / "collector_ebay_reconstructed_recall_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    authority = pd.read_csv(AUTHORITY, dtype=str, encoding="utf-8-sig").fillna("")
    current = pd.read_csv(CURRENT, dtype=str, encoding="utf-8-sig").fillna("")
    history = pd.read_csv(HISTORY, dtype=str, encoding="utf-8-sig").fillna("")
    contracts = pd.read_csv(CONTRACTS, dtype=str, encoding="utf-8-sig").fillna("")
    name_col = "box_name" if "box_name" in authority.columns else "governed_box_name"
    item_col = "item_id" if "item_id" in current.columns else "ebay_item_id"
    for frame in (authority, current, history, contracts):
        frame["tcgplayer_product_id"] = frame["tcgplayer_product_id"].map(norm_id)

    rows = []
    historical_only_rows = []
    for _, auth in authority.iterrows():
        pid = norm_id(auth["tcgplayer_product_id"])
        name = str(auth[name_col]).strip()
        current_ids = set(current.loc[current["tcgplayer_product_id"] == pid, item_col].astype(str))
        hist_subset = history[history["tcgplayer_product_id"] == pid]
        historical_ids = set(hist_subset["ebay_item_id"].astype(str))
        overlap = current_ids & historical_ids
        historical_only = historical_ids - current_ids
        current_only = current_ids - historical_ids
        rows.append({
            "tcgplayer_product_id": pid,
            "governed_box_name": name,
            "current_sample_unique_item_ids": len(current_ids),
            "historical_unique_item_ids": len(historical_ids),
            "overlap_item_ids": len(overlap),
            "historical_only_item_ids": len(historical_only),
            "current_only_item_ids": len(current_only),
            "recoverable_evidence_overlap_rate": round(len(overlap) / len(historical_ids), 6) if historical_ids else "",
            "query_variant_count": int((contracts["tcgplayer_product_id"] == pid).sum()),
            "acquisition_recall_status": "RECALL_GAP_EVIDENCE" if historical_only else "NO_HISTORICAL_GAP_DETECTED_NOT_CERTIFIED",
            "true_zero_authorized": False,
        })
        if historical_only:
            subset = hist_subset[hist_subset["ebay_item_id"].isin(historical_only)]
            for _, row in subset.iterrows():
                historical_only_rows.append({
                    "tcgplayer_product_id": pid,
                    "governed_box_name": name,
                    "ebay_item_id": row.get("ebay_item_id", ""),
                    "title": row.get("title", ""),
                    "match_state": row.get("match_state", ""),
                    "ebay_query": row.get("ebay_query", ""),
                    "observed_at_utc": row.get("observed_at_utc", ""),
                    "source_path": row.get("source_path", ""),
                })

    evidence = pd.DataFrame(rows)
    evidence.to_csv(OUT / "collector_ebay_valid_recall_evidence.csv", index=False)
    pd.DataFrame(historical_only_rows).drop_duplicates().to_csv(OUT / "collector_ebay_historical_only_listing_evidence.csv", index=False)

    canary_candidates = evidence.copy()
    canary_candidates["priority"] = canary_candidates["historical_only_item_ids"].astype(int) * 1000
    canary_candidates["priority"] += (canary_candidates["current_sample_unique_item_ids"].astype(int) == 0).astype(int) * 500
    canary_candidates["priority"] += canary_candidates["query_variant_count"].astype(int)
    canaries = canary_candidates.sort_values(["priority", "historical_only_item_ids"], ascending=False).head(6).copy()
    canaries["canary_role"] = canaries.apply(lambda row: "ZERO_CURRENT_WITH_HISTORY" if int(row["current_sample_unique_item_ids"]) == 0 and int(row["historical_unique_item_ids"]) > 0 else ("HIGH_HISTORICAL_GAP" if int(row["historical_only_item_ids"]) > 0 else "CONTROL"), axis=1)
    canaries["live_canary_authorized"] = True
    canaries.to_csv(OUT / "collector_ebay_valid_high_recall_canary_plan.csv", index=False)

    products_with_gap = int((evidence["historical_only_item_ids"] > 0).sum())
    zero_with_history = int(((evidence["current_sample_unique_item_ids"] == 0) & (evidence["historical_unique_item_ids"] > 0)).sum())
    reconstructed_products = int((evidence["historical_unique_item_ids"] > 0).sum())
    valid = reconstructed_products > 0
    summary = {
        "block_name": "Collector eBay Reconstructed Recall Validation",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "governed_products": len(evidence),
        "products_with_reconstructed_history": reconstructed_products,
        "products_with_historical_only_item_ids": products_with_gap,
        "current_zero_products_with_historical_evidence": zero_with_history,
        "historical_only_listing_rows": len(pd.DataFrame(historical_only_rows).drop_duplicates()),
        "valid_canary_products": len(canaries),
        "historical_recall_comparison_valid": valid,
        "acquisition_recall_certified": False,
        "live_canary_authorized": valid,
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_VALID_OFFLINE_RECALL_COMPARISON_CANARY_READY" if valid else "REVIEW_REQUIRED",
    }
    (OUT / "collector_ebay_reconstructed_recall_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if valid else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
