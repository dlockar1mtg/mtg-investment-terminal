"""Adjudicate eBay item IDs accepted for multiple governed Collector products.

This block is offline and fail closed. A duplicated accepted item remains accepted
for one product only when product-specific evidence has a unique, material winner.
Otherwise every competing mapping is removed from accepted supply and preserved in
an ambiguity ledger. The day-one ledgers, 50-product snapshot, hashes, summary, and
manifest are rebuilt from the hardened replay authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"
REPLAY_DIR = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_hardened_replay"
ACQ_DIR = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_acquisition"
REPLAY = REPLAY_DIR / "collector_ebay_full_universe_hardened_replay.csv"
REPLAY_SUMMARY = REPLAY_DIR / "collector_ebay_full_universe_hardened_replay_summary.json"
ACQ_SUMMARY = ACQ_DIR / "collector_ebay_full_universe_acquisition_summary.json"
PRODUCT_CERT = ACQ_DIR / "collector_ebay_full_universe_product_certification.csv"
KNOWN_UNSAFE_ITEM = "v1|198519464141|0"
TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
STOP = {
    "magic", "the", "gathering", "mtg", "collector", "booster", "box", "display",
    "sealed", "factory", "new", "universes", "beyond", "edition",
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Adjudicate duplicated accepted eBay items for day-one baseline")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--winner-margin", type=float, default=0.08)
    return p


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_id(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("TCGPLAYER-"):
        text = text.removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def tokens(value: object) -> set[str]:
    return {t for t in TOKEN_RE.findall(str(value or "").lower()) if t not in STOP and len(t) > 1}


def coverage(title: object, product_name: object) -> float:
    p = tokens(product_name)
    if not p:
        return 0.0
    return len(tokens(title) & p) / len(p)


def numeric(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value or "").strip())
    except ValueError:
        return default


def main() -> int:
    args = parser().parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    required = (REPLAY, REPLAY_SUMMARY, ACQ_SUMMARY, PRODUCT_CERT)
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        print(json.dumps({"status": "REQUIRED_INPUT_MISSING", "missing_inputs": missing}, indent=2))
        return 1 if args.strict else 0

    replay_summary = json.loads(REPLAY_SUMMARY.read_text(encoding="utf-8"))
    acq_summary = json.loads(ACQ_SUMMARY.read_text(encoding="utf-8"))
    if replay_summary.get("status") != "PASS_FULL_UNIVERSE_HARDENED_REPLAY_BASELINE_READY":
        raise RuntimeError("Hardened replay is not authorized for baseline promotion")
    if acq_summary.get("acquisition_recall_certified") is not True:
        raise RuntimeError("Acquisition recall is not certified")

    replay = pd.read_csv(REPLAY, dtype=str, encoding="utf-8-sig").fillna("")
    products = pd.read_csv(PRODUCT_CERT, dtype=str, encoding="utf-8-sig").fillna("")
    replay["tcgplayer_product_id"] = replay["resolved_tcgplayer_product_id"].map(norm_id)
    products["tcgplayer_product_id"] = products["tcgplayer_product_id"].map(norm_id)
    products = products.drop_duplicates("tcgplayer_product_id")
    if len(products) != 50:
        raise RuntimeError(f"Expected 50 governed products; found {len(products)}")

    accepted = replay[replay["match_state"] == "ACCEPTED"].copy()
    review = replay[replay["match_state"] == "REVIEW"].copy()
    rejected = replay[replay["match_state"] == "REJECTED"].copy()
    duplicate_ids = [item for item, group in accepted.groupby("ebay_item_id") if group["tcgplayer_product_id"].nunique() > 1]

    kept_indices: set[int] = set(accepted.index)
    ambiguity_rows: list[dict[str, object]] = []
    adjudication_rows: list[dict[str, object]] = []
    resolved_unique_winners = 0
    unresolved_items = 0

    for item_id in duplicate_ids:
        group = accepted[accepted["ebay_item_id"] == item_id].copy()
        ranked: list[tuple[int, float, float, float]] = []
        for idx, row in group.iterrows():
            match_score = numeric(row.get("match_score"))
            identity_coverage = coverage(row.get("title"), row.get("canonical_product_name"))
            composite = 0.65 * match_score + 0.35 * identity_coverage
            ranked.append((idx, composite, match_score, identity_coverage))
        ranked.sort(key=lambda x: (-x[1], -x[2], -x[3], str(group.loc[x[0], "tcgplayer_product_id"])))
        top = ranked[0]
        second = ranked[1]
        margin = top[1] - second[1]
        unique_winner = margin >= args.winner_margin and top[2] >= second[2]

        if unique_winner:
            resolved_unique_winners += 1
            winner_idx = top[0]
            for idx, composite, match_score, identity_coverage in ranked:
                action = "KEEP_ACCEPTED_UNIQUE_EVIDENCE_WINNER" if idx == winner_idx else "REMOVE_ACCEPTED_LOSING_MAPPING"
                if idx != winner_idx:
                    kept_indices.discard(idx)
                    ambiguity_rows.append({**group.loc[idx].to_dict(), "adjudication_disposition": "CROSS_PRODUCT_LOSING_MAPPING_EXCLUDED"})
                adjudication_rows.append({
                    "ebay_item_id": item_id,
                    "tcgplayer_product_id": group.loc[idx, "tcgplayer_product_id"],
                    "canonical_product_name": group.loc[idx].get("canonical_product_name", ""),
                    "title": group.loc[idx].get("title", ""),
                    "match_score": match_score,
                    "identity_token_coverage": round(identity_coverage, 6),
                    "composite_evidence_score": round(composite, 6),
                    "winner_margin": round(margin, 6),
                    "adjudication_action": action,
                })
        else:
            unresolved_items += 1
            for idx, composite, match_score, identity_coverage in ranked:
                kept_indices.discard(idx)
                ambiguity_rows.append({**group.loc[idx].to_dict(), "adjudication_disposition": "CROSS_PRODUCT_AMBIGUOUS_EXCLUDED"})
                adjudication_rows.append({
                    "ebay_item_id": item_id,
                    "tcgplayer_product_id": group.loc[idx, "tcgplayer_product_id"],
                    "canonical_product_name": group.loc[idx].get("canonical_product_name", ""),
                    "title": group.loc[idx].get("title", ""),
                    "match_score": match_score,
                    "identity_token_coverage": round(identity_coverage, 6),
                    "composite_evidence_score": round(composite, 6),
                    "winner_margin": round(margin, 6),
                    "adjudication_action": "REMOVE_ACCEPTED_AMBIGUOUS_MAPPING",
                })

    accepted_final = accepted.loc[sorted(kept_indices)].copy()
    ambiguity = pd.DataFrame(ambiguity_rows)
    adjudication = pd.DataFrame(adjudication_rows)

    baseline_observed_at = acq_summary.get("generated_at", "")
    baseline_id = "collector-ebay-day-one-" + str(baseline_observed_at)[:10].replace("-", "")
    source_hash = sha256_file(REPLAY)
    for frame, disposition in ((accepted_final, "ACCEPTED_BASELINE"), (review, "REVIEW_EXCLUDED")):
        for col in ("baseline_id", "baseline_observed_at_utc", "baseline_disposition", "matcher_version", "source_replay_sha256"):
            if col in frame.columns:
                frame.drop(columns=[col], inplace=True)
        frame.insert(0, "baseline_id", baseline_id)
        frame.insert(1, "baseline_observed_at_utc", baseline_observed_at)
        frame.insert(2, "baseline_disposition", disposition)
        frame.insert(3, "matcher_version", replay_summary.get("matcher_version", "precision-v3-universal"))
        frame.insert(4, "source_replay_sha256", source_hash)

    accepted_path = BASE / "collector_ebay_day_one_accepted_listing_ledger.csv"
    review_path = BASE / "collector_ebay_day_one_review_ledger.csv"
    ambiguity_path = BASE / "collector_ebay_day_one_cross_product_ambiguity_ledger.csv"
    adjudication_path = BASE / "collector_ebay_day_one_multi_product_adjudication.csv"
    accepted_final.to_csv(accepted_path, index=False)
    review.to_csv(review_path, index=False)
    ambiguity.to_csv(ambiguity_path, index=False)
    adjudication.to_csv(adjudication_path, index=False)

    snapshot_rows: list[dict[str, object]] = []
    for _, product in products.iterrows():
        pid = norm_id(product["tcgplayer_product_id"])
        a = accepted_final[accepted_final["tcgplayer_product_id"] == pid]
        v = review[review["tcgplayer_product_id"] == pid]
        r = rejected[rejected["tcgplayer_product_id"] == pid]
        amb = ambiguity[ambiguity.get("tcgplayer_product_id", pd.Series(dtype=str)) == pid] if not ambiguity.empty else ambiguity
        prices = pd.to_numeric(a.get("landed_price", a.get("price", pd.Series(dtype=str))), errors="coerce").dropna()
        seller_col = next((c for c in ("seller_hash", "seller_id_hash", "seller_id", "seller_username") if c in a.columns), None)
        sellers = a[seller_col].astype(str).replace("", pd.NA).dropna().nunique() if seller_col else 0
        snapshot_rows.append({
            "baseline_id": baseline_id,
            "baseline_observed_at_utc": baseline_observed_at,
            "tcgplayer_product_id": pid,
            "governed_box_name": product["governed_box_name"],
            "accepted_listing_count": len(a),
            "review_listing_count": len(v),
            "rejected_listing_count": len(r),
            "cross_product_ambiguity_excluded_count": len(amb),
            "observable_seller_count": int(sellers),
            "lowest_accepted_landed_price": float(prices.min()) if not prices.empty else "",
            "median_accepted_landed_price": float(prices.median()) if not prices.empty else "",
            "highest_accepted_landed_price": float(prices.max()) if not prices.empty else "",
            "accepted_price_observation_count": int(len(prices)),
            "supply_observation_state": "OBSERVED_ACCEPTED_SUPPLY" if len(a) else "ZERO_ACCEPTED_LISTINGS_OBSERVED",
            "zero_supply_interpretation": "OBSERVED_ZERO_WITHIN_CERTIFIED_ACQUISITION_CONTRACT" if len(a) == 0 else "NOT_APPLICABLE",
            "matcher_version": replay_summary.get("matcher_version", "precision-v3-universal"),
        })
    snapshot = pd.DataFrame(snapshot_rows)
    snapshot_path = BASE / "collector_ebay_day_one_product_supply_snapshot.csv"
    snapshot.to_csv(snapshot_path, index=False)

    remaining_multi = int(sum(1 for _, g in accepted_final.groupby("ebay_item_id") if g["tcgplayer_product_id"].nunique() > 1))
    composite_overlap = len(set(zip(accepted_final["tcgplayer_product_id"], accepted_final["ebay_item_id"])) & set(zip(review["tcgplayer_product_id"], review["ebay_item_id"])))
    unsafe_present = KNOWN_UNSAFE_ITEM in set(accepted_final["ebay_item_id"])
    accepted_reconciled = int(snapshot["accepted_listing_count"].sum()) == len(accepted_final)
    review_reconciled = int(snapshot["review_listing_count"].sum()) == len(review)
    integrity = (
        len(snapshot) == 50
        and remaining_multi == 0
        and composite_overlap == 0
        and not unsafe_present
        and accepted_reconciled
        and review_reconciled
        and len(accepted_final) + len(ambiguity) == len(accepted)
    )

    hashes = {
        "source_hardened_replay_sha256": source_hash,
        "accepted_listing_ledger_sha256": sha256_file(accepted_path),
        "review_ledger_sha256": sha256_file(review_path),
        "cross_product_ambiguity_ledger_sha256": sha256_file(ambiguity_path),
        "multi_product_adjudication_sha256": sha256_file(adjudication_path),
        "product_supply_snapshot_sha256": sha256_file(snapshot_path),
    }
    summary = {
        "block_name": "Collector eBay Day-One Multi-Product Accepted Adjudication",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "baseline_id": baseline_id,
        "original_accepted_rows": len(accepted),
        "final_accepted_rows": len(accepted_final),
        "review_rows": len(review),
        "cross_product_ambiguity_excluded_rows": len(ambiguity),
        "duplicated_accepted_item_ids_adjudicated": len(duplicate_ids),
        "unique_evidence_winners": resolved_unique_winners,
        "unresolved_ambiguous_item_ids": unresolved_items,
        "accepted_item_ids_mapped_to_multiple_products": remaining_multi,
        "accepted_review_composite_overlap_rows": composite_overlap,
        "known_unsafe_item_in_accepted_ledger": unsafe_present,
        "governed_product_rows": len(snapshot),
        "accepted_count_reconciled": accepted_reconciled,
        "review_count_reconciled": review_reconciled,
        "baseline_integrity_passed": integrity,
        "baseline_promoted": integrity,
        "continuity_accumulation_authorized": integrity,
        "scarcity_feature_calculation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "artifact_hashes": hashes,
        "status": "PASS_DAY_ONE_MULTI_PRODUCT_ADJUDICATION_BASELINE_PROMOTED" if integrity else "FAIL_DAY_ONE_MULTI_PRODUCT_ADJUDICATION",
    }
    summary_path = BASE / "collector_ebay_day_one_supply_baseline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "baseline_id": baseline_id,
        "immutable_source": str(REPLAY.relative_to(ROOT)),
        "artifacts": {
            "accepted_listing_ledger": str(accepted_path.relative_to(ROOT)),
            "review_ledger": str(review_path.relative_to(ROOT)),
            "cross_product_ambiguity_ledger": str(ambiguity_path.relative_to(ROOT)),
            "multi_product_adjudication": str(adjudication_path.relative_to(ROOT)),
            "product_supply_snapshot": str(snapshot_path.relative_to(ROOT)),
            "summary": str(summary_path.relative_to(ROOT)),
        },
        "hashes": {**hashes, "summary_sha256": sha256_file(summary_path)},
        "governance": {
            "accepted_item_must_map_to_one_product": True,
            "ambiguous_cross_product_accepts_excluded_from_supply": True,
            "unique_winner_requires_material_evidence_margin": args.winner_margin,
            "review_rows_excluded_from_supply": True,
            "zero_products_retained": True,
            "continuity_may_start_from_this_baseline_only": integrity,
            "forecasting_authorized": False,
            "purchase_recommendations_authorized": False,
            "uip_delivery_authorized": False,
        },
    }
    (BASE / "collector_ebay_day_one_supply_baseline_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if integrity else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
