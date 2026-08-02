"""Build a governed Collector eBay baseline-to-current continuity comparison.

This module does not collect or classify listings. It accepts only already-certified
accepted/review/ambiguity ledgers and a 50-product snapshot for a later observation.
It compares them with the immutable day-one baseline and emits listing-event and
product-level continuity evidence. Listing exits are observational absences, not sales.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_continuity_comparison"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build certified Collector eBay continuity comparison")
    p.add_argument("--current-accepted-ledger", type=Path, required=True)
    p.add_argument("--current-review-ledger", type=Path, required=True)
    p.add_argument("--current-ambiguity-ledger", type=Path, required=True)
    p.add_argument("--current-product-snapshot", type=Path, required=True)
    p.add_argument("--current-summary", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--strict", action="store_true")
    return p


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric(value: object) -> float | None:
    try:
        text = str(value or "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    baseline_paths = {
        "accepted": BASELINE / "collector_ebay_day_one_accepted_listing_ledger.csv",
        "review": BASELINE / "collector_ebay_day_one_review_ledger.csv",
        "ambiguity": BASELINE / "collector_ebay_day_one_cross_product_ambiguity_ledger.csv",
        "snapshot": BASELINE / "collector_ebay_day_one_product_supply_snapshot.csv",
        "summary": BASELINE / "collector_ebay_day_one_supply_baseline_summary.json",
        "manifest": BASELINE / "collector_ebay_day_one_supply_baseline_manifest.json",
    }
    current_paths = {
        "accepted": args.current_accepted_ledger,
        "review": args.current_review_ledger,
        "ambiguity": args.current_ambiguity_ledger,
        "snapshot": args.current_product_snapshot,
        "summary": args.current_summary,
    }
    missing = [str(p) for p in [*baseline_paths.values(), *current_paths.values()] if not p.is_file()]
    if missing:
        summary = {
            "block_name": "Collector eBay Continuity Comparison",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "missing_inputs": missing,
            "comparison_certified": False,
            "status": "REQUIRED_INPUT_MISSING",
        }
        (out / "collector_ebay_continuity_comparison_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    baseline_summary = json.loads(baseline_paths["summary"].read_text(encoding="utf-8"))
    current_summary = json.loads(current_paths["summary"].read_text(encoding="utf-8"))
    baseline_authorized = baseline_summary.get("baseline_promoted") is True
    current_authorized = (
        current_summary.get("baseline_integrity_passed") is True
        or current_summary.get("observation_integrity_passed") is True
    ) and int(current_summary.get("accepted_item_ids_mapped_to_multiple_products", 0)) == 0

    b_acc = pd.read_csv(baseline_paths["accepted"], dtype=str, encoding="utf-8-sig").fillna("")
    c_acc = pd.read_csv(current_paths["accepted"], dtype=str, encoding="utf-8-sig").fillna("")
    b_rev = pd.read_csv(baseline_paths["review"], dtype=str, encoding="utf-8-sig").fillna("")
    c_rev = pd.read_csv(current_paths["review"], dtype=str, encoding="utf-8-sig").fillna("")
    b_amb = pd.read_csv(baseline_paths["ambiguity"], dtype=str, encoding="utf-8-sig").fillna("")
    c_amb = pd.read_csv(current_paths["ambiguity"], dtype=str, encoding="utf-8-sig").fillna("")
    b_snap = pd.read_csv(baseline_paths["snapshot"], dtype=str, encoding="utf-8-sig").fillna("")
    c_snap = pd.read_csv(current_paths["snapshot"], dtype=str, encoding="utf-8-sig").fillna("")

    required_cols = {"tcgplayer_product_id", "ebay_item_id"}
    schema_ok = required_cols.issubset(b_acc.columns) and required_cols.issubset(c_acc.columns)
    snapshots_ok = len(b_snap) == 50 and len(c_snap) == 50 and b_snap["tcgplayer_product_id"].nunique() == 50 and c_snap["tcgplayer_product_id"].nunique() == 50
    accepted_unique = c_acc.groupby("ebay_item_id")["tcgplayer_product_id"].nunique().max() <= 1 if not c_acc.empty else True

    b_keys = set(zip(b_acc["tcgplayer_product_id"], b_acc["ebay_item_id"])) if schema_ok else set()
    c_keys = set(zip(c_acc["tcgplayer_product_id"], c_acc["ebay_item_id"])) if schema_ok else set()
    persistent = b_keys & c_keys
    entered = c_keys - b_keys
    exited = b_keys - c_keys

    event_rows: list[dict[str, object]] = []
    for state, keys in (("PERSISTENT", persistent), ("ENTERED_OBSERVATION", entered), ("EXITED_OBSERVATION", exited)):
        for pid, item in sorted(keys):
            event_rows.append({
                "tcgplayer_product_id": pid,
                "ebay_item_id": item,
                "continuity_event": state,
                "interpretation": (
                    "OBSERVED_IN_BOTH_CERTIFIED_ACQUISITIONS" if state == "PERSISTENT"
                    else "NEWLY_OBSERVED_IN_CURRENT_CERTIFIED_ACQUISITION" if state == "ENTERED_OBSERVATION"
                    else "NOT_OBSERVED_IN_CURRENT_CERTIFIED_ACQUISITION_NOT_PROOF_OF_SALE"
                ),
            })
    events = pd.DataFrame(event_rows, columns=["tcgplayer_product_id", "ebay_item_id", "continuity_event", "interpretation"])
    events_path = out / "collector_ebay_continuity_listing_events.csv"
    events.to_csv(events_path, index=False)

    product_rows: list[dict[str, object]] = []
    pids = sorted(set(b_snap["tcgplayer_product_id"]) | set(c_snap["tcgplayer_product_id"]))
    for pid in pids:
        b = b_snap[b_snap["tcgplayer_product_id"] == pid].iloc[0] if not b_snap[b_snap["tcgplayer_product_id"] == pid].empty else pd.Series(dtype=str)
        c = c_snap[c_snap["tcgplayer_product_id"] == pid].iloc[0] if not c_snap[c_snap["tcgplayer_product_id"] == pid].empty else pd.Series(dtype=str)
        b_count = int(float(b.get("accepted_listing_count", 0) or 0))
        c_count = int(float(c.get("accepted_listing_count", 0) or 0))
        p_count = sum(1 for key in persistent if key[0] == pid)
        e_count = sum(1 for key in entered if key[0] == pid)
        x_count = sum(1 for key in exited if key[0] == pid)
        b_med = numeric(b.get("median_accepted_landed_price"))
        c_med = numeric(c.get("median_accepted_landed_price"))
        b_min = numeric(b.get("lowest_accepted_landed_price"))
        c_min = numeric(c.get("lowest_accepted_landed_price"))
        product_rows.append({
            "tcgplayer_product_id": pid,
            "governed_box_name": c.get("governed_box_name", b.get("governed_box_name", "")),
            "baseline_accepted_listing_count": b_count,
            "current_accepted_listing_count": c_count,
            "accepted_supply_change": c_count - b_count,
            "persistent_listing_count": p_count,
            "entered_listing_count": e_count,
            "exited_listing_count": x_count,
            "listing_persistence_rate": round(p_count / b_count, 6) if b_count else "",
            "baseline_observable_seller_count": int(float(b.get("observable_seller_count", 0) or 0)),
            "current_observable_seller_count": int(float(c.get("observable_seller_count", 0) or 0)),
            "observable_seller_count_change": int(float(c.get("observable_seller_count", 0) or 0)) - int(float(b.get("observable_seller_count", 0) or 0)),
            "baseline_lowest_landed_price": b_min if b_min is not None else "",
            "current_lowest_landed_price": c_min if c_min is not None else "",
            "lowest_landed_price_change": (c_min - b_min) if c_min is not None and b_min is not None else "",
            "baseline_median_landed_price": b_med if b_med is not None else "",
            "current_median_landed_price": c_med if c_med is not None else "",
            "median_landed_price_change": (c_med - b_med) if c_med is not None and b_med is not None else "",
            "baseline_review_count": int(float(b.get("review_listing_count", 0) or 0)),
            "current_review_count": int(float(c.get("review_listing_count", 0) or 0)),
            "review_count_change": int(float(c.get("review_listing_count", 0) or 0)) - int(float(b.get("review_listing_count", 0) or 0)),
            "baseline_ambiguity_excluded_count": int(float(b.get("cross_product_ambiguity_excluded_count", 0) or 0)),
            "current_ambiguity_excluded_count": int(float(c.get("cross_product_ambiguity_excluded_count", 0) or 0)),
        })
    products = pd.DataFrame(product_rows)
    product_path = out / "collector_ebay_continuity_product_metrics.csv"
    products.to_csv(product_path, index=False)

    comparison_certified = bool(baseline_authorized and current_authorized and schema_ok and snapshots_ok and accepted_unique and len(products) == 50)
    summary = {
        "block_name": "Collector eBay Continuity Comparison",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "baseline_authorized": baseline_authorized,
        "current_observation_authorized": current_authorized,
        "schema_contract_passed": schema_ok,
        "snapshot_contract_passed": snapshots_ok,
        "accepted_item_unique_product_mapping_passed": bool(accepted_unique),
        "baseline_accepted_rows": len(b_acc),
        "current_accepted_rows": len(c_acc),
        "persistent_listing_rows": len(persistent),
        "entered_listing_rows": len(entered),
        "exited_listing_rows": len(exited),
        "governed_product_rows": len(products),
        "comparison_certified": comparison_certified,
        "continuity_observation_count": 2 if comparison_certified else 1,
        "scarcity_feature_calculation_authorized": False,
        "forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "artifact_hashes": {
            "baseline_accepted_sha256": sha256_file(baseline_paths["accepted"]),
            "current_accepted_sha256": sha256_file(current_paths["accepted"]),
            "listing_events_sha256": sha256_file(events_path),
            "product_metrics_sha256": sha256_file(product_path),
        },
        "status": "PASS_CONTINUITY_COMPARISON_CERTIFIED" if comparison_certified else "FAIL_CONTINUITY_COMPARISON_CONTRACT",
    }
    summary_path = out / "collector_ebay_continuity_comparison_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if comparison_certified else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
