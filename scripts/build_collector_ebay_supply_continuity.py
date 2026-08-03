"""Build full-universe Collector eBay coverage, continuity baseline, and shadow scarcity features.

Offline-only. Uses the identity-complete certified daily ledger and governed Collector authority.
Trend-dependent scarcity components remain unavailable until at least two certified snapshot dates exist.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DAILY_ROOT = ROOT / "data/governance/permanence/certification/collector_ebay_daily_supply"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_supply_continuity"
LEDGER = DAILY_ROOT / "collector_ebay_certified_daily_listing_ledger.csv"
SNAPSHOT = DAILY_ROOT / "collector_ebay_certified_product_supply_snapshot.csv"
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_official_release_date_authority/collector_official_release_date_authority.csv"
SHADOW_COVERAGE = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection/collector_ebay_product_supply_snapshot_shadow.csv"
HISTORY = OUT / "collector_ebay_certified_listing_history.csv"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build Collector eBay continuity baseline")
    p.add_argument("--ledger", type=Path, default=LEDGER)
    p.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    p.add_argument("--authority", type=Path, default=AUTHORITY)
    p.add_argument("--shadow-coverage", type=Path, default=SHADOW_COVERAGE)
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


def clamp01(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, value))


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    required = [args.ledger, args.snapshot, args.authority]
    missing = [str(p.resolve()) for p in required if not p.resolve().is_file()]
    if missing:
        summary = {
            "block_name": "Collector eBay Supply Continuity Baseline",
            "generated_at": generated.isoformat(),
            "offline_only": True,
            "quota_calls": 0,
            "missing_required_inputs": missing,
            "status": "REQUIRED_INPUTS_MISSING",
        }
        (out / "collector_ebay_supply_continuity_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    ledger = pd.read_csv(args.ledger.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    snapshot = pd.read_csv(args.snapshot.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    authority = pd.read_csv(args.authority.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
    for frame in (ledger, snapshot, authority):
        frame["tcgplayer_product_id"] = frame["tcgplayer_product_id"].map(norm_id)

    name_col = next((c for c in ["box_name", "governed_box_name", "canonical_product_name"] if c in authority.columns), None)
    if name_col is None:
        raise ValueError("Authority file has no governed product-name column")
    authority = authority[["tcgplayer_product_id", name_col] + [c for c in ["release_date", "lifecycle_state"] if c in authority.columns]].copy()
    authority = authority.rename(columns={name_col: "governed_box_name"}).drop_duplicates("tcgplayer_product_id")

    queried_ids: set[str] = set()
    if args.shadow_coverage.resolve().is_file():
        shadow = pd.read_csv(args.shadow_coverage.resolve(), dtype=str, encoding="utf-8-sig").fillna("")
        if "tcgplayer_product_id" in shadow.columns:
            queried_ids = set(shadow["tcgplayer_product_id"].map(norm_id))

    snap_by_id = {r["tcgplayer_product_id"]: r for _, r in snapshot.iterrows()}
    full_rows: list[dict[str, object]] = []
    snapshot_dates = sorted(set(x for x in ledger.get("snapshot_date", pd.Series(dtype=str)).astype(str) if x))
    current_date = snapshot_dates[-1] if snapshot_dates else ""
    for _, auth in authority.iterrows():
        pid = auth["tcgplayer_product_id"]
        observed = snap_by_id.get(pid)
        query_completed = pid in queried_ids or observed is not None
        if observed is not None:
            row = dict(observed)
            row["observation_status"] = "OBSERVED_ACCEPTED_SUPPLY"
            row["query_completed"] = True
            row["zero_supply_interpretation"] = ""
        else:
            row = {
                "snapshot_date": current_date,
                "tcgplayer_product_id": pid,
                "governed_box_name": auth["governed_box_name"],
                "accepted_active_listing_count": 0,
                "unique_seller_count": 0,
                "listed_display_quantity_lower_bound": 0,
                "listed_display_quantity_estimate": 0 if query_completed else "",
                "quantity_estimate_complete": bool(query_completed),
                "minimum_delivered_asking_price": "",
                "median_delivered_asking_price": "",
                "maximum_delivered_asking_price": "",
                "asking_price_iqr": "",
                "seller_quantity_hhi": "",
                "listing_quantity_hhi": "",
                "tcg_market_price": "",
                "listings_within_10pct_tcg_market": 0 if query_completed else "",
                "price_depth_near_tcg_market_share": "",
                "supply_snapshot_status": "CERTIFIED_ZERO_ACCEPTED_SUPPLY" if query_completed else "QUERY_EVIDENCE_MISSING",
                "observation_status": "ZERO_ACCEPTED_LISTINGS" if query_completed else "NOT_OBSERVED_QUERY_UNCONFIRMED",
                "query_completed": bool(query_completed),
                "zero_supply_interpretation": "SEARCH_COMPLETED_NO_PRODUCTION_ACCEPTED_LISTINGS" if query_completed else "NO_QUERY_COMPLETION_EVIDENCE",
            }
        row["governed_box_name"] = auth["governed_box_name"]
        full_rows.append(row)

    full = pd.DataFrame(full_rows).sort_values(["governed_box_name", "tcgplayer_product_id"])
    full.to_csv(out / "collector_ebay_full_universe_daily_supply_snapshot.csv", index=False)

    if HISTORY.is_file():
        history = pd.read_csv(HISTORY, dtype=str, encoding="utf-8-sig").fillna("")
        combined = pd.concat([history, ledger], ignore_index=True, sort=False)
    else:
        combined = ledger.copy()
    key_cols = [c for c in ["snapshot_date", "tcgplayer_product_id", "ebay_item_id"] if c in combined.columns]
    combined = combined.drop_duplicates(key_cols, keep="last").sort_values(key_cols)
    combined.to_csv(HISTORY, index=False)

    continuity_rows: list[dict[str, object]] = []
    for (pid, item_id), group in combined.groupby(["tcgplayer_product_id", "ebay_item_id"], dropna=False):
        dates = sorted(set(x for x in group["snapshot_date"].astype(str) if x))
        continuity_rows.append({
            "tcgplayer_product_id": pid,
            "governed_box_name": group["governed_box_name"].iloc[-1],
            "ebay_item_id": item_id,
            "first_seen_date": dates[0] if dates else "",
            "last_seen_date": dates[-1] if dates else "",
            "certified_days_observed": len(dates),
            "is_present_latest_snapshot": bool(current_date and current_date in dates),
            "entry_event_on_latest_date": bool(len(dates) == 1 and current_date in dates),
            "exit_event_confirmed": False,
            "relist_event_confirmed": False,
            "continuity_status": "BASELINE_FIRST_OBSERVATION" if len(snapshot_dates) <= 1 else "ACTIVE_CONTINUITY_RECORD",
        })
    continuity = pd.DataFrame(continuity_rows)
    continuity.to_csv(out / "collector_ebay_listing_continuity.csv", index=False)

    certified_days = sorted(set(x for x in combined.get("snapshot_date", pd.Series(dtype=str)).astype(str) if x))
    trend_available = len(certified_days) >= 2
    feature_rows: list[dict[str, object]] = []
    for _, row in full.iterrows():
        listings = num(row.get("accepted_active_listing_count")) or 0.0
        quantity = num(row.get("listed_display_quantity_lower_bound")) or 0.0
        sellers = num(row.get("unique_seller_count")) or 0.0
        seller_hhi = num(row.get("seller_quantity_hhi"))
        price_depth = num(row.get("price_depth_near_tcg_market_share"))
        depth_scarcity = 1.0 / (1.0 + quantity)
        listing_scarcity = 1.0 / (1.0 + listings)
        seller_scarcity = 1.0 / (1.0 + sellers)
        concentration = seller_hhi if seller_hhi is not None else (1.0 if listings == 1 else None)
        marketplace_depth_component = round((0.5 * depth_scarcity + 0.3 * listing_scarcity + 0.2 * seller_scarcity) * 100, 4)
        concentration_component = round(clamp01(concentration) * 100, 4) if concentration is not None else ""
        price_pressure_component = round((1.0 - clamp01(price_depth)) * 100, 4) if price_depth is not None else ""
        available = [x for x in [marketplace_depth_component, concentration_component, price_pressure_component] if x != ""]
        static_score = round(sum(float(x) for x in available) / len(available), 4) if available else ""
        feature_rows.append({
            "snapshot_date": row.get("snapshot_date", current_date),
            "tcgplayer_product_id": row["tcgplayer_product_id"],
            "governed_box_name": row["governed_box_name"],
            "observation_status": row["observation_status"],
            "certified_snapshot_days": len(certified_days),
            "marketplace_supply_depth_component": marketplace_depth_component,
            "seller_concentration_component": concentration_component,
            "price_pressure_component": price_pressure_component,
            "supply_trend_component": "",
            "turnover_component": "",
            "static_scarcity_baseline_score": static_score,
            "supply_scarcity_index_v1": "",
            "trend_features_available": trend_available,
            "feature_status": "SHADOW_STATIC_BASELINE_ONLY" if not trend_available else "SHADOW_MULTI_DAY_FEATURES_AVAILABLE",
            "forecast_eligible": False,
            "purchase_recommendation_eligible": False,
        })
    features = pd.DataFrame(feature_rows)
    features.to_csv(out / "collector_supply_scarcity_shadow_features.csv", index=False)

    blank_names = int(full["governed_box_name"].astype(str).str.strip().eq("").sum())
    query_missing = int((~full["query_completed"].astype(bool)).sum())
    status = "PASS_COLLECTOR_EBAY_SUPPLY_CONTINUITY_BASELINE" if len(full) == len(authority) and blank_names == 0 and query_missing == 0 else "REVIEW_REQUIRED"
    summary = {
        "block_name": "Collector eBay Supply Continuity Baseline",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "governed_products": len(authority),
        "full_universe_snapshot_rows": len(full),
        "products_with_observed_accepted_supply": int((full["observation_status"] == "OBSERVED_ACCEPTED_SUPPLY").sum()),
        "products_with_zero_accepted_listings": int((full["observation_status"] == "ZERO_ACCEPTED_LISTINGS").sum()),
        "products_missing_query_completion_evidence": query_missing,
        "blank_governed_names": blank_names,
        "certified_listing_history_rows": len(combined),
        "listing_continuity_rows": len(continuity),
        "certified_snapshot_days": len(certified_days),
        "trend_features_available": trend_available,
        "full_supply_scarcity_index_authorized": False,
        "static_scarcity_baseline_written": True,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": status,
    }
    (out / "collector_ebay_supply_continuity_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    passed = status.startswith("PASS_")
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
