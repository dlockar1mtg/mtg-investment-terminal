"""Repair and certify day-one baseline overlap integrity.

The original promotion compared accepted and review ledgers by eBay item ID alone.
The same marketplace listing may be evaluated against multiple governed products,
so disposition overlap must be tested on the composite identity
(tcgplayer_product_id, ebay_item_id). Cross-product item reuse remains auditable
and accepted listings must still map to exactly one governed product.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"
ACCEPTED = OUT / "collector_ebay_day_one_accepted_listing_ledger.csv"
REVIEW = OUT / "collector_ebay_day_one_review_ledger.csv"
SNAPSHOT = OUT / "collector_ebay_day_one_product_supply_snapshot.csv"
SUMMARY = OUT / "collector_ebay_day_one_supply_baseline_summary.json"
MANIFEST = OUT / "collector_ebay_day_one_supply_baseline_manifest.json"
AUDIT = OUT / "collector_ebay_day_one_cross_product_overlap_audit.csv"
KNOWN_UNSAFE_ITEM = "v1|198519464141|0"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Repair Collector eBay day-one baseline overlap integrity")
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument("--strict", action="store_true")
    return p


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm(value: object) -> str:
    return str(value or "").strip()


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    generated = datetime.now(timezone.utc)
    accepted_path = out / ACCEPTED.name
    review_path = out / REVIEW.name
    snapshot_path = out / SNAPSHOT.name
    summary_path = out / SUMMARY.name
    manifest_path = out / MANIFEST.name
    audit_path = out / AUDIT.name

    required = (accepted_path, review_path, snapshot_path, summary_path, manifest_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        result = {
            "block_name": "Collector eBay Day-One Baseline Composite Overlap Repair",
            "block_version": "1.0.0",
            "generated_at": generated.isoformat(),
            "offline_only": True,
            "missing_inputs": missing,
            "baseline_promoted": False,
            "status": "REQUIRED_INPUT_MISSING",
        }
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    accepted = pd.read_csv(accepted_path, dtype=str, encoding="utf-8-sig").fillna("")
    review = pd.read_csv(review_path, dtype=str, encoding="utf-8-sig").fillna("")
    snapshot = pd.read_csv(snapshot_path, dtype=str, encoding="utf-8-sig").fillna("")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    required_columns = {"tcgplayer_product_id", "ebay_item_id"}
    for label, frame in (("accepted", accepted), ("review", review)):
        missing_columns = sorted(required_columns - set(frame.columns))
        if missing_columns:
            raise RuntimeError(f"{label} ledger missing required columns: {missing_columns}")

    accepted["_product_id"] = accepted["tcgplayer_product_id"].map(norm)
    accepted["_item_id"] = accepted["ebay_item_id"].map(norm)
    review["_product_id"] = review["tcgplayer_product_id"].map(norm)
    review["_item_id"] = review["ebay_item_id"].map(norm)

    accepted_composite = set(zip(accepted["_product_id"], accepted["_item_id"]))
    review_composite = set(zip(review["_product_id"], review["_item_id"]))
    composite_overlap = sorted(accepted_composite & review_composite)

    accepted_items = set(accepted["_item_id"])
    review_items = set(review["_item_id"])
    cross_disposition_item_ids = sorted(accepted_items & review_items)

    accepted_product_counts = accepted.groupby("_item_id")["_product_id"].nunique()
    accepted_multi_product_item_ids = sorted(accepted_product_counts[accepted_product_counts > 1].index.tolist())

    audit_rows: list[dict[str, object]] = []
    for item_id in cross_disposition_item_ids:
        accepted_rows = accepted[accepted["_item_id"] == item_id]
        review_rows = review[review["_item_id"] == item_id]
        accepted_products = sorted(set(accepted_rows["_product_id"]))
        review_products = sorted(set(review_rows["_product_id"]))
        same_product_overlap = sorted(set(accepted_products) & set(review_products))
        audit_rows.append({
            "ebay_item_id": item_id,
            "accepted_product_ids": "|".join(accepted_products),
            "review_product_ids": "|".join(review_products),
            "accepted_product_count": len(accepted_products),
            "review_product_count": len(review_products),
            "same_product_disposition_overlap": bool(same_product_overlap),
            "same_product_overlap_ids": "|".join(same_product_overlap),
            "governance_interpretation": (
                "INVALID_SAME_PRODUCT_OVERLAP" if same_product_overlap
                else "VALID_CROSS_PRODUCT_CANDIDATE_REUSE"
            ),
        })
    audit = pd.DataFrame(audit_rows, columns=[
        "ebay_item_id",
        "accepted_product_ids",
        "review_product_ids",
        "accepted_product_count",
        "review_product_count",
        "same_product_disposition_overlap",
        "same_product_overlap_ids",
        "governance_interpretation",
    ])
    audit.to_csv(audit_path, index=False)

    accepted_count = len(accepted)
    review_count = len(review)
    snapshot_count = len(snapshot)
    accepted_sum = int(pd.to_numeric(snapshot["accepted_listing_count"], errors="coerce").fillna(0).sum())
    review_sum = int(pd.to_numeric(snapshot["review_listing_count"], errors="coerce").fillna(0).sum())
    unsafe_present = KNOWN_UNSAFE_ITEM in accepted_items
    duplicate_accepted_composites = int(accepted.duplicated(["_product_id", "_item_id"]).sum())

    integrity_pass = (
        accepted_count == 572
        and review_count == 303
        and snapshot_count == 50
        and accepted_sum == accepted_count
        and review_sum == review_count
        and duplicate_accepted_composites == 0
        and len(composite_overlap) == 0
        and len(accepted_multi_product_item_ids) == 0
        and not unsafe_present
    )

    summary.update({
        "block_version": "1.0.1",
        "integrity_repaired_at": generated.isoformat(),
        "overlap_identity_contract": "TCGPLAYER_PRODUCT_ID_PLUS_EBAY_ITEM_ID",
        "accepted_review_overlap_rows": len(composite_overlap),
        "accepted_review_composite_overlap_rows": len(composite_overlap),
        "accepted_review_cross_product_item_ids": len(cross_disposition_item_ids),
        "accepted_item_ids_mapped_to_multiple_products": len(accepted_multi_product_item_ids),
        "duplicate_accepted_rows": duplicate_accepted_composites,
        "known_unsafe_item_in_accepted_ledger": unsafe_present,
        "accepted_count_reconciled": accepted_sum == accepted_count,
        "review_count_reconciled": review_sum == review_count,
        "baseline_integrity_passed": integrity_pass,
        "baseline_promoted": integrity_pass,
        "continuity_accumulation_authorized": integrity_pass,
        "scarcity_feature_calculation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "cross_product_overlap_audit_path": str(audit_path.relative_to(ROOT)),
        "status": (
            "PASS_DAY_ONE_SUPPLY_BASELINE_PROMOTED_CONTINUITY_READY"
            if integrity_pass else "FAIL_DAY_ONE_SUPPLY_BASELINE_INTEGRITY"
        ),
    })
    summary.setdefault("artifact_hashes", {})["cross_product_overlap_audit_sha256"] = sha256_file(audit_path)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    manifest.setdefault("artifacts", {})["cross_product_overlap_audit"] = str(audit_path.relative_to(ROOT))
    manifest.setdefault("hashes", {})["cross_product_overlap_audit_sha256"] = sha256_file(audit_path)
    manifest["hashes"]["summary_sha256"] = sha256_file(summary_path)
    manifest.setdefault("governance", {}).update({
        "listing_identity_contract": "TCGPLAYER_PRODUCT_ID_PLUS_EBAY_ITEM_ID",
        "cross_product_candidate_reuse_audited": True,
        "same_product_accepted_review_overlap": len(composite_overlap) > 0,
        "accepted_item_must_map_to_one_product": True,
        "continuity_may_start_from_this_baseline_only": integrity_pass,
        "forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = {
        "block_name": "Collector eBay Day-One Baseline Composite Overlap Repair",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "accepted_listing_rows": accepted_count,
        "review_listing_rows": review_count,
        "governed_product_rows": snapshot_count,
        "accepted_review_composite_overlap_rows": len(composite_overlap),
        "accepted_review_cross_product_item_ids": len(cross_disposition_item_ids),
        "accepted_item_ids_mapped_to_multiple_products": len(accepted_multi_product_item_ids),
        "known_unsafe_item_in_accepted_ledger": unsafe_present,
        "baseline_integrity_passed": integrity_pass,
        "baseline_promoted": integrity_pass,
        "continuity_accumulation_authorized": integrity_pass,
        "status": (
            "PASS_DAY_ONE_BASELINE_COMPOSITE_OVERLAP_REPAIRED"
            if integrity_pass else "FAIL_DAY_ONE_BASELINE_COMPOSITE_OVERLAP_REPAIR"
        ),
    }
    print(json.dumps(result, indent=2))
    return 0 if integrity_pass else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
