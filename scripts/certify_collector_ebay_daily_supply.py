"""Certify reconciled Collector eBay listing decisions and build the first daily supply snapshot.

Offline-only. Uses the precision-v3-universal replay as matching authority and the
Browse API shadow artifacts only for quantity, seller, price, and raw-payload evidence.
Forecasting, recommendations, and UIP delivery remain unauthorized.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RECON_ROOT = ROOT / "data/governance/permanence/certification/collector_ebay_authority_reconciliation"
SUPPLY_ROOT = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_daily_supply"
RECLASSIFIED = RECON_ROOT / "collector_ebay_shadow_reclassified.csv"
SHADOW = SUPPLY_ROOT / "collector_ebay_listing_observations_shadow.csv"
MANIFEST = SUPPLY_ROOT / "collector_ebay_raw_payload_manifest.csv"
PACKAGING = ROOT / "data/governance/permanence/certification/collector_packaging_normalization/collector_packaging_normalization.csv"
CURRENT_PRICE = ROOT / "data/governance/permanence/certification/collector_tcgcsv_current_price/collector_tcgcsv_current_price.csv"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Certify Collector eBay daily supply")
    p.add_argument("--reclassified", type=Path, default=RECLASSIFIED)
    p.add_argument("--shadow", type=Path, default=SHADOW)
    p.add_argument("--manifest", type=Path, default=MANIFEST)
    p.add_argument("--packaging", type=Path, default=PACKAGING)
    p.add_argument("--current-price", type=Path, default=CURRENT_PRICE)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--strict", action="store_true")
    return p


def norm_id(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def num(value: object) -> float | None:
    try:
        if pd.isna(value) or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def adjudicate(title: str, reasons: str, transition: str) -> tuple[str, str]:
    low = title.lower()
    reason_set = set(x for x in reasons.split("|") if x)
    if transition != "ACCEPTED->REJECTED":
        return "NOT_REQUIRED", "PRODUCTION_DECISION_CONTROLS"
    if "presale" in reason_set:
        return "CONFIRMED_REJECTED", "CONFIRMED_PRESALE"
    if "omega box" in low or "omega booster box" in low or "single_pack_collector_product" in reason_set:
        if re.search(r"\b(?:4x|4\s+boxes?)\b", low):
            return "CONFIRMED_REJECTED", "CONFIRMED_MULTI_UNIT_WRONG_CONFIGURATION"
        return "CONFIRMED_REJECTED", "CONFIRMED_WRONG_CONFIGURATION_OMEGA_SINGLE_PACK"
    if re.search(r"\b(?:4x|4\s+boxes?)\b", low):
        return "CONFIRMED_REJECTED", "CONFIRMED_MULTI_DISPLAY_LOT"
    if "missing_mtg_identity" in reason_set:
        return "CONFIRMED_REJECTED", "CONFIRMED_INSUFFICIENT_MTG_IDENTITY_EVIDENCE"
    return "REVIEW_REQUIRED", "UNRESOLVED_DOWNGRADE_REASON"


def hhi(values: list[float]) -> float | None:
    total = sum(values)
    if total <= 0:
        return None
    return round(sum((v / total) ** 2 for v in values), 6)


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    required = [args.reclassified, args.shadow, args.packaging]
    missing = [str(p) for p in required if not p.resolve().is_file()]
    if missing:
        summary = {"block_name": "Collector eBay Daily Supply Certification", "generated_at": generated.isoformat(), "missing_required_inputs": missing, "status": "REQUIRED_INPUTS_MISSING"}
        (out / "collector_ebay_daily_supply_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    replay = pd.read_csv(args.reclassified.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    shadow = pd.read_csv(args.shadow.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    packaging = pd.read_csv(args.packaging.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    for frame in (replay, shadow, packaging):
        if "tcgplayer_product_id" in frame.columns:
            frame["tcgplayer_product_id"] = frame["tcgplayer_product_id"].map(norm_id)

    replay["ebay_item_id"] = replay.get("ebay_item_id", replay.get("item_id", "")).astype(str)
    shadow["ebay_item_id"] = shadow.get("item_id", "").astype(str)
    merged = replay.merge(shadow, on=["tcgplayer_product_id", "ebay_item_id"], how="left", suffixes=("_production", "_shadow"), validate="one_to_one")

    adjudications = []
    for _, row in merged.iterrows():
        status, reason = adjudicate(
            str(row.get("title_production", row.get("title_shadow", ""))),
            str(row.get("production_reason_codes", "")),
            str(row.get("classification_transition", "")),
        )
        adjudications.append((status, reason))
    merged["adjudication_status"] = [x[0] for x in adjudications]
    merged["adjudication_reason"] = [x[1] for x in adjudications]

    downgrade = merged[merged["classification_transition"] == "ACCEPTED->REJECTED"].copy()
    downgrade_fields = [c for c in ["tcgplayer_product_id", "governed_box_name", "ebay_item_id", "title_production", "production_reason_codes", "classification_transition", "adjudication_status", "adjudication_reason"] if c in downgrade.columns]
    downgrade[downgrade_fields].to_csv(out / "collector_ebay_downgrade_adjudication.csv", index=False)

    unresolved = int((downgrade["adjudication_status"] != "CONFIRMED_REJECTED").sum())
    accepted = merged[merged["production_decision"] == "ACCEPTED"].copy()

    # Preserve one authoritative listing ledger row per observed listing.
    ledger = pd.DataFrame({
        "snapshot_date": pd.to_datetime(accepted.get("observed_at_shadow", accepted.get("observed_at_utc", generated.isoformat())), errors="coerce", utc=True).dt.date.astype(str),
        "retrieval_id": accepted.get("retrieval_id", accepted.get("source_run_id", "")),
        "tcgplayer_product_id": accepted["tcgplayer_product_id"],
        "governed_box_name": accepted.get("governed_box_name", ""),
        "ebay_item_id": accepted["ebay_item_id"],
        "title": accepted.get("title_production", accepted.get("title_shadow", "")),
        "production_decision": accepted["production_decision"],
        "production_reason_codes": accepted.get("production_reason_codes", ""),
        "match_score": accepted.get("match_score", ""),
        "seller_pseudonym_sha256": accepted.get("seller_pseudonym_sha256", accepted.get("seller_hash", "")),
        "price_value": accepted.get("price_value", accepted.get("price", "")),
        "price_currency": accepted.get("price_currency", accepted.get("currency", "")),
        "delivered_price_estimate": accepted.get("delivered_price_estimate", accepted.get("landed_price", "")),
        "estimated_quantity": accepted.get("estimated_quantity", ""),
        "listed_quantity_lower_bound": accepted.get("listed_quantity_lower_bound", ""),
        "quantity_thresholded": accepted.get("quantity_thresholded", ""),
        "estimated_sold_quantity": accepted.get("estimated_sold_quantity", ""),
        "item_creation_date": accepted.get("item_creation_date", ""),
        "item_end_date": accepted.get("item_end_date", ""),
        "matcher_version": accepted.get("matcher_version", "precision-v3-universal"),
        "certification_status": "CERTIFIED_ACCEPTED_LISTING",
    })

    if args.manifest.resolve().is_file():
        manifest = pd.read_csv(args.manifest.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
        if "item_id" in manifest.columns:
            detail = manifest[manifest.get("request_type", "") == "DETAIL"].copy()
            detail["ebay_item_id"] = detail["item_id"].astype(str)
            detail = detail.sort_values("ebay_item_id").drop_duplicates("ebay_item_id", keep="last")
            cols = [c for c in ["ebay_item_id", "sha256", "raw_path", "vault_path"] if c in detail.columns]
            ledger = ledger.merge(detail[cols], on="ebay_item_id", how="left")
            ledger = ledger.rename(columns={"sha256": "raw_payload_sha256", "raw_path": "raw_payload_path", "vault_path": "vault_payload_path"})

    pack_cols = [c for c in ["tcgplayer_product_id", "collector_packs_per_display", "configuration_quantity_status"] if c in packaging.columns]
    ledger = ledger.merge(packaging[pack_cols].drop_duplicates("tcgplayer_product_id"), on="tcgplayer_product_id", how="left")
    ledger.to_csv(out / "collector_ebay_certified_daily_listing_ledger.csv", index=False)

    market_by_id: dict[str, float] = {}
    if args.current_price.resolve().is_file():
        prices = pd.read_csv(args.current_price.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
        if "tcgplayer_product_id" in prices.columns:
            prices["tcgplayer_product_id"] = prices["tcgplayer_product_id"].map(norm_id)
            price_col = next((c for c in ["market_price", "tcg_market_price", "current_market_price"] if c in prices.columns), None)
            if price_col:
                market_by_id = {r["tcgplayer_product_id"]: num(r[price_col]) for _, r in prices.iterrows() if num(r[price_col]) is not None}

    snapshots = []
    for (pid, name), group in ledger.groupby(["tcgplayer_product_id", "governed_box_name"], dropna=False):
        delivered = [num(v) for v in group["delivered_price_estimate"]]
        delivered = [v for v in delivered if v is not None]
        lower = [num(v) or 1.0 for v in group["listed_quantity_lower_bound"]]
        exact = [num(v) for v in group["estimated_quantity"]]
        exact_known = [v for v in exact if v is not None]
        seller_qty = group.assign(_q=lower).groupby("seller_pseudonym_sha256", dropna=False)["_q"].sum().tolist()
        sellers = [s for s in group["seller_pseudonym_sha256"].astype(str).tolist() if s]
        q1 = pd.Series(delivered).quantile(0.25) if delivered else None
        q3 = pd.Series(delivered).quantile(0.75) if delivered else None
        market = market_by_id.get(str(pid))
        near_market = sum(1 for value in delivered if market and 0.9 * market <= value <= 1.1 * market)
        snapshots.append({
            "snapshot_date": group["snapshot_date"].iloc[0] if len(group) else "",
            "tcgplayer_product_id": pid,
            "governed_box_name": name,
            "accepted_active_listing_count": len(group),
            "unique_seller_count": len(set(sellers)),
            "listed_display_quantity_lower_bound": round(sum(lower), 4),
            "listed_display_quantity_estimate": round(sum(exact_known), 4) if len(exact_known) == len(group) else "",
            "quantity_estimate_complete": len(exact_known) == len(group),
            "minimum_delivered_asking_price": min(delivered) if delivered else "",
            "median_delivered_asking_price": float(pd.Series(delivered).median()) if delivered else "",
            "maximum_delivered_asking_price": max(delivered) if delivered else "",
            "asking_price_iqr": float(q3 - q1) if delivered else "",
            "seller_quantity_hhi": hhi([float(x) for x in seller_qty]),
            "listing_quantity_hhi": hhi([float(x) for x in lower]),
            "tcg_market_price": market if market is not None else "",
            "listings_within_10pct_tcg_market": near_market if market is not None else "",
            "price_depth_near_tcg_market_share": round(near_market / len(delivered), 6) if market is not None and delivered else "",
            "supply_snapshot_status": "CERTIFIED_DAILY_SUPPLY_SNAPSHOT",
        })
    snapshot = pd.DataFrame(snapshots)
    snapshot.to_csv(out / "collector_ebay_certified_product_supply_snapshot.csv", index=False)

    summary = {
        "block_name": "Collector eBay Daily Supply Certification",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "production_matcher_version": "precision-v3-universal",
        "listing_rows_received": len(merged),
        "accepted_listing_rows_certified": len(ledger),
        "rejected_listing_rows_excluded": int((merged["production_decision"] == "REJECTED").sum()),
        "production_review_rows": int((merged["production_decision"] == "REVIEW").sum()),
        "downgrade_rows": len(downgrade),
        "downgrades_confirmed_rejected": int((downgrade["adjudication_status"] == "CONFIRMED_REJECTED").sum()),
        "downgrades_unresolved": unresolved,
        "product_supply_snapshot_rows": len(snapshot),
        "listing_ledger_written": True,
        "product_supply_snapshot_written": True,
        "daily_ledger_authority": "PRECISION_V3_UNIVERSAL_PLUS_BROWSE_DETAIL_ENRICHMENT",
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_DAILY_SUPPLY_CERTIFICATION" if unresolved == 0 and len(ledger) > 0 else "REVIEW_REQUIRED",
    }
    (out / "collector_ebay_daily_supply_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    passed = summary["status"].startswith("PASS_")
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
