"""Promote the certified hardened Collector eBay acquisition into day-one supply.

The hardened replay is the only listing-classification authority for this block.
Accepted rows become the immutable production-eligible ledger, REVIEW rows remain
isolated, and every governed product receives one snapshot row, including zeros.
No live collection occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPLAY_DIR = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_hardened_replay"
ACQUISITION_DIR = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_acquisition"
REPLAY_CSV = REPLAY_DIR / "collector_ebay_full_universe_hardened_replay.csv"
REPLAY_SUMMARY = REPLAY_DIR / "collector_ebay_full_universe_hardened_replay_summary.json"
ACQUISITION_SUMMARY = ACQUISITION_DIR / "collector_ebay_full_universe_acquisition_summary.json"
PRODUCT_CERT = ACQUISITION_DIR / "collector_ebay_full_universe_product_certification.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"
KNOWN_UNSAFE_ITEM = "v1|198519464141|0"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Promote hardened Collector eBay day-one supply baseline")
    p.add_argument("--replay-csv", type=Path, default=REPLAY_CSV)
    p.add_argument("--replay-summary", type=Path, default=REPLAY_SUMMARY)
    p.add_argument("--acquisition-summary", type=Path, default=ACQUISITION_SUMMARY)
    p.add_argument("--product-certification", type=Path, default=PRODUCT_CERT)
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--strict", action="store_true")
    return p


def norm_id(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("TCGPLAYER-"):
        text = text.removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def pick(frame: pd.DataFrame, candidates: tuple[str, ...], required: bool = True) -> str | None:
    for column in candidates:
        if column in frame.columns:
            return column
    if required:
        raise RuntimeError(f"Required column missing. Expected one of: {candidates}")
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)

    required = (args.replay_csv, args.replay_summary, args.acquisition_summary, args.product_certification)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        summary = {
            "block_name": "Collector eBay Day-One Supply Baseline Promotion",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "offline_only": True,
            "missing_inputs": missing,
            "baseline_promoted": False,
            "status": "REQUIRED_INPUT_MISSING",
        }
        (out / "collector_ebay_day_one_supply_baseline_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    replay_summary = json.loads(args.replay_summary.read_text(encoding="utf-8"))
    acquisition_summary = json.loads(args.acquisition_summary.read_text(encoding="utf-8"))
    replay_authorized = (
        replay_summary.get("status") == "PASS_FULL_UNIVERSE_HARDENED_REPLAY_BASELINE_READY"
        and replay_summary.get("replay_complete") is True
        and replay_summary.get("supply_baseline_authorized") is True
        and int(replay_summary.get("unsafe_accepted_rows", -1)) == 0
        and replay_summary.get("known_unsafe_row_downgraded") is True
    )
    acquisition_certified = (
        acquisition_summary.get("status") == "PASS_FULL_UNIVERSE_ACQUISITION_CERTIFIED_BASELINE_READY"
        and acquisition_summary.get("acquisition_recall_certified") is True
        and int(acquisition_summary.get("governed_products", 0)) == 50
        and int(acquisition_summary.get("coverage_rows", 0)) == 50
        and int(acquisition_summary.get("source_errors", -1)) == 0
    )
    if not replay_authorized or not acquisition_certified:
        summary = {
            "block_name": "Collector eBay Day-One Supply Baseline Promotion",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "offline_only": True,
            "hardened_replay_authorized": replay_authorized,
            "acquisition_recall_certified": acquisition_certified,
            "baseline_promoted": False,
            "status": "UPSTREAM_AUTHORIZATION_MISSING",
        }
        (out / "collector_ebay_day_one_supply_baseline_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1 if args.strict else 0

    replay = pd.read_csv(args.replay_csv, dtype=str, encoding="utf-8-sig").fillna("")
    products = pd.read_csv(args.product_certification, dtype=str, encoding="utf-8-sig").fillna("")
    state_col = pick(replay, ("match_state",))
    item_col = pick(replay, ("ebay_item_id", "item_id"))
    pid_col = pick(replay, ("resolved_tcgplayer_product_id", "tcgplayer_product_id", "canonical_product_id"))
    product_pid_col = pick(products, ("tcgplayer_product_id",))
    product_name_col = pick(products, ("governed_box_name", "box_name"))
    title_col = pick(replay, ("title",), required=False)
    seller_col = pick(replay, ("seller_hash", "seller_id_hash", "seller_id", "seller_username"), required=False)
    landed_col = pick(replay, ("landed_price", "total_price", "price_plus_shipping", "price"), required=False)
    observed_col = pick(replay, ("observed_at_utc", "observed_at", "collected_at_utc"), required=False)

    replay["tcgplayer_product_id"] = replay[pid_col].map(norm_id)
    products["tcgplayer_product_id"] = products[product_pid_col].map(norm_id)
    products = products.drop_duplicates("tcgplayer_product_id").copy()
    if len(products) != 50:
        raise RuntimeError(f"Expected 50 governed products in product certification; found {len(products)}")

    accepted = replay[replay[state_col] == "ACCEPTED"].copy()
    review = replay[replay[state_col] == "REVIEW"].copy()
    rejected = replay[replay[state_col] == "REJECTED"].copy()

    duplicate_accepted = int(accepted.duplicated(["tcgplayer_product_id", item_col]).sum())
    accepted = accepted.drop_duplicates(["tcgplayer_product_id", item_col]).copy()
    review = review.drop_duplicates(["tcgplayer_product_id", item_col]).copy()
    accepted_review_overlap = sorted(set(accepted[item_col]) & set(review[item_col]))
    unsafe_present = KNOWN_UNSAFE_ITEM in set(accepted[item_col].astype(str))

    baseline_observed_at = acquisition_summary.get("generated_at", "")
    baseline_id = "collector-ebay-day-one-" + str(baseline_observed_at)[:10].replace("-", "")
    for frame, disposition in ((accepted, "ACCEPTED_BASELINE"), (review, "REVIEW_EXCLUDED")):
        frame.insert(0, "baseline_id", baseline_id)
        frame.insert(1, "baseline_observed_at_utc", baseline_observed_at)
        frame.insert(2, "baseline_disposition", disposition)
        frame.insert(3, "matcher_version", replay_summary.get("matcher_version", "precision-v3-universal"))
        frame.insert(4, "source_replay_sha256", sha256_file(args.replay_csv))

    accepted_path = out / "collector_ebay_day_one_accepted_listing_ledger.csv"
    review_path = out / "collector_ebay_day_one_review_ledger.csv"
    accepted.to_csv(accepted_path, index=False)
    review.to_csv(review_path, index=False)

    snapshot_rows: list[dict[str, object]] = []
    for _, product in products.iterrows():
        pid = norm_id(product["tcgplayer_product_id"])
        product_accepted = accepted[accepted["tcgplayer_product_id"] == pid]
        product_review = review[review["tcgplayer_product_id"] == pid]
        product_rejected = rejected[rejected["tcgplayer_product_id"] == pid]
        prices = numeric(product_accepted[landed_col]) if landed_col else pd.Series(dtype=float)
        valid_prices = prices.dropna()
        sellers = (
            product_accepted[seller_col].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
            if seller_col else 0
        )
        observation_values = (
            product_accepted[observed_col].astype(str).replace("", pd.NA).dropna()
            if observed_col else pd.Series(dtype=str)
        )
        snapshot_rows.append({
            "baseline_id": baseline_id,
            "baseline_observed_at_utc": baseline_observed_at,
            "tcgplayer_product_id": pid,
            "governed_box_name": product[product_name_col],
            "accepted_listing_count": len(product_accepted),
            "review_listing_count": len(product_review),
            "rejected_listing_count": len(product_rejected),
            "observable_seller_count": int(sellers),
            "lowest_accepted_landed_price": float(valid_prices.min()) if not valid_prices.empty else "",
            "median_accepted_landed_price": float(valid_prices.median()) if not valid_prices.empty else "",
            "highest_accepted_landed_price": float(valid_prices.max()) if not valid_prices.empty else "",
            "accepted_price_observation_count": int(len(valid_prices)),
            "first_listing_observed_at_utc": observation_values.min() if not observation_values.empty else "",
            "last_listing_observed_at_utc": observation_values.max() if not observation_values.empty else "",
            "supply_observation_state": "OBSERVED_ACCEPTED_SUPPLY" if len(product_accepted) else "ZERO_ACCEPTED_LISTINGS_OBSERVED",
            "zero_supply_interpretation": "OBSERVED_ZERO_WITHIN_CERTIFIED_ACQUISITION_CONTRACT" if len(product_accepted) == 0 else "NOT_APPLICABLE",
            "matcher_version": replay_summary.get("matcher_version", "precision-v3-universal"),
        })
    snapshot = pd.DataFrame(snapshot_rows)
    snapshot_path = out / "collector_ebay_day_one_product_supply_snapshot.csv"
    snapshot.to_csv(snapshot_path, index=False)

    hashes = {
        "source_hardened_replay_sha256": sha256_file(args.replay_csv),
        "source_replay_summary_sha256": sha256_file(args.replay_summary),
        "source_acquisition_summary_sha256": sha256_file(args.acquisition_summary),
        "source_product_certification_sha256": sha256_file(args.product_certification),
        "accepted_listing_ledger_sha256": sha256_file(accepted_path),
        "review_ledger_sha256": sha256_file(review_path),
        "product_supply_snapshot_sha256": sha256_file(snapshot_path),
    }
    zero_products = snapshot.loc[snapshot["accepted_listing_count"] == 0, "tcgplayer_product_id"].astype(str).tolist()
    integrity_pass = (
        len(replay) == int(replay_summary.get("replayed_rows", -1))
        and len(accepted) == int(replay_summary.get("state_counts", {}).get("ACCEPTED", -1))
        and len(review) == int(replay_summary.get("state_counts", {}).get("REVIEW", -1))
        and len(rejected) == int(replay_summary.get("state_counts", {}).get("REJECTED", -1))
        and len(snapshot) == 50
        and duplicate_accepted == 0
        and not accepted_review_overlap
        and not unsafe_present
        and int(snapshot["accepted_listing_count"].sum()) == len(accepted)
        and int(snapshot["review_listing_count"].sum()) == len(review)
    )
    summary = {
        "block_name": "Collector eBay Day-One Supply Baseline Promotion",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "baseline_id": baseline_id,
        "baseline_observed_at_utc": baseline_observed_at,
        "matcher_version": replay_summary.get("matcher_version", "precision-v3-universal"),
        "source_replayed_rows": len(replay),
        "accepted_listing_rows": len(accepted),
        "review_listing_rows": len(review),
        "rejected_listing_rows": len(rejected),
        "governed_product_rows": len(snapshot),
        "products_with_accepted_supply": int((snapshot["accepted_listing_count"] > 0).sum()),
        "products_with_zero_accepted_supply": int((snapshot["accepted_listing_count"] == 0).sum()),
        "zero_accepted_supply_product_ids": zero_products,
        "duplicate_accepted_rows": duplicate_accepted,
        "accepted_review_overlap_rows": len(accepted_review_overlap),
        "known_unsafe_item_in_accepted_ledger": unsafe_present,
        "accepted_count_reconciled": int(snapshot["accepted_listing_count"].sum()) == len(accepted),
        "review_count_reconciled": int(snapshot["review_listing_count"].sum()) == len(review),
        "baseline_integrity_passed": integrity_pass,
        "baseline_promoted": integrity_pass,
        "continuity_accumulation_authorized": integrity_pass,
        "scarcity_feature_calculation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "artifact_hashes": hashes,
        "status": "PASS_DAY_ONE_SUPPLY_BASELINE_PROMOTED_CONTINUITY_READY" if integrity_pass else "FAIL_DAY_ONE_SUPPLY_BASELINE_INTEGRITY",
    }
    summary_path = out / "collector_ebay_day_one_supply_baseline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "baseline_id": baseline_id,
        "immutable_source": str(args.replay_csv.relative_to(ROOT)),
        "artifacts": {
            "accepted_listing_ledger": str(accepted_path.relative_to(ROOT)),
            "review_ledger": str(review_path.relative_to(ROOT)),
            "product_supply_snapshot": str(snapshot_path.relative_to(ROOT)),
            "summary": str(summary_path.relative_to(ROOT)),
        },
        "hashes": {**hashes, "summary_sha256": sha256_file(summary_path)},
        "governance": {
            "review_rows_excluded_from_supply": True,
            "zero_products_retained": True,
            "continuity_may_start_from_this_baseline_only": integrity_pass,
            "forecasting_authorized": False,
            "purchase_recommendations_authorized": False,
            "uip_delivery_authorized": False,
        },
    }
    (out / "collector_ebay_day_one_supply_baseline_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if integrity_pass else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
