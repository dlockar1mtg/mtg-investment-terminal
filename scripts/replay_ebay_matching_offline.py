from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_matching import CanonicalProduct, MatchResult
from terminal2.market_sources.ebay_precision_v2 import identity_match_listing as precision_v2_match
from terminal2.market_sources.ebay_precision_v3 import identity_match_listing as precision_v3_match

STATE_RANK = {"REJECTED": 0, "REVIEW": 1, "ACCEPTED": 2}
MIGRATION_MATCHER = "precision-v3-universal"
BASELINE_MATCHER = "precision-v2"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def product_from_row(row: dict[str, str]) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id=row.get("canonical_product_id", ""),
        canonical_product_name=row.get("canonical_product_name", ""),
        canonical_set_name=row.get("canonical_set_name", ""),
        product_class=row.get("product_class", "SEALED_SECRET_LAIR"),
        tcgplayer_product_id=row.get("tcgplayer_product_id", ""),
        release_date=row.get("release_date", ""),
        ebay_query=row.get("ebay_query", ""),
    )


def item_from_row(row: dict[str, str]) -> dict[str, object]:
    return {
        "itemId": row.get("ebay_item_id", ""),
        "title": row.get("title", ""),
        "itemWebUrl": row.get("item_url", ""),
        "price": {
            "value": row.get("price", "0") or "0",
            "currency": row.get("currency", "USD") or "USD",
        },
        "condition": row.get("condition", ""),
    }


def _run_matcher(
    matcher: Callable[[CanonicalProduct, dict[str, object], str, str], MatchResult],
    row: dict[str, str],
) -> MatchResult:
    return matcher(
        product_from_row(row),
        item_from_row(row),
        row.get("source_run_id", "OFFLINE-REPLAY"),
        row.get("observed_at_utc", ""),
    )


def _clamp_downgrade_only(previous_state: str, candidate_state: str) -> str:
    previous = previous_state if previous_state in STATE_RANK else "REJECTED"
    candidate = candidate_state if candidate_state in STATE_RANK else "REJECTED"
    return candidate if STATE_RANK[candidate] <= STATE_RANK[previous] else previous


def _safe_score(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _transition(old: str, new: str) -> str:
    return f"{old}->{new}"


def replay_row(row: dict[str, str]) -> dict[str, object]:
    saved_state = row.get("match_state", "")
    saved_score_text = str(row.get("match_score", ""))
    saved_score = _safe_score(saved_score_text)

    v2 = _run_matcher(precision_v2_match, row)
    v3 = _run_matcher(precision_v3_match, row)

    migrated_state = _clamp_downgrade_only(saved_state, v3.match_state)
    migrated_score = v3.match_score
    migration_reasons = [value for value in v3.exclusion_reasons.split("|") if value]
    if migrated_state != v3.match_state:
        migration_reasons.append("offline_upgrade_blocked")
        migrated_score = min(saved_score, v3.match_score)

    updated: dict[str, object] = dict(row)
    updated.update(
        {
            "saved_match_score": saved_score_text,
            "saved_match_state": saved_state,
            "saved_exclusion_reasons": row.get("exclusion_reasons", ""),
            "precision_v2_match_score": round(v2.match_score, 4),
            "precision_v2_match_state": v2.match_state,
            "precision_v2_exclusion_reasons": v2.exclusion_reasons,
            "precision_v3_match_score": round(v3.match_score, 4),
            "precision_v3_match_state": v3.match_state,
            "precision_v3_exclusion_reasons": v3.exclusion_reasons,
            "match_score": round(migrated_score, 4),
            "match_state": migrated_state,
            "exclusion_reasons": "|".join(dict.fromkeys(migration_reasons)),
            "saved_to_v2_transition": _transition(saved_state, v2.match_state),
            "v2_to_v3_transition": _transition(v2.match_state, v3.match_state),
            "saved_to_migrated_transition": _transition(saved_state, migrated_state),
            "classification_changed": str(saved_state != migrated_state).lower(),
            "v2_v3_changed": str(v2.match_state != v3.match_state).lower(),
            "evidence_changed": str(
                saved_score_text != str(round(migrated_score, 4))
                or row.get("exclusion_reasons", "") != updated.get("exclusion_reasons", "")
            ).lower(),
            "migration_matcher_version": MIGRATION_MATCHER,
            "migration_policy_mode": "downgrade_only",
        }
    )
    updated["evidence_changed"] = str(
        saved_score_text != str(updated["match_score"])
        or row.get("exclusion_reasons", "") != updated["exclusion_reasons"]
    ).lower()
    return updated


def _reason_counts(rows: list[dict[str, object]], field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        for reason in str(row.get(field, "")).split("|"):
            if reason:
                counts[reason] += 1
    return counts


def run(input_root: Path, output_root: Path) -> dict[str, object]:
    listing_files = sorted(input_root.rglob("ebay_listing_match_results_*.csv"))
    if not listing_files:
        raise FileNotFoundError(f"No eBay listing evidence found under {input_root}")

    source_rows: list[dict[str, str]] = []
    for path in listing_files:
        for row in read_csv(path):
            enriched = dict(row)
            enriched["offline_source_file"] = str(path.resolve())
            source_rows.append(enriched)

    replayed = [replay_row(row) for row in source_rows]

    state_saved = Counter(row.get("match_state", "") for row in source_rows)
    state_v2 = Counter(str(row.get("precision_v2_match_state", "")) for row in replayed)
    state_v3 = Counter(str(row.get("precision_v3_match_state", "")) for row in replayed)
    state_migrated = Counter(str(row.get("match_state", "")) for row in replayed)
    saved_to_v2 = Counter(str(row["saved_to_v2_transition"]) for row in replayed)
    v2_to_v3 = Counter(str(row["v2_to_v3_transition"]) for row in replayed)
    saved_to_migrated = Counter(str(row["saved_to_migrated_transition"]) for row in replayed)

    upgrade_count = sum(
        STATE_RANK.get(str(row.get("match_state", "")), -1)
        > STATE_RANK.get(str(row.get("saved_match_state", "")), -1)
        for row in replayed
    )
    v2_to_v3_upgrade_count = sum(
        STATE_RANK.get(str(row.get("precision_v3_match_state", "")), -1)
        > STATE_RANK.get(str(row.get("precision_v2_match_state", "")), -1)
        for row in replayed
    )

    by_product: dict[str, Counter[str]] = defaultdict(Counter)
    product_names: dict[str, str] = {}
    for row in replayed:
        product_id = str(row.get("canonical_product_id", ""))
        product_names.setdefault(product_id, str(row.get("canonical_product_name", "")))
        by_product[product_id][str(row.get("match_state", ""))] += 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = output_root / f"migration_{stamp}"
    output.mkdir(parents=True, exist_ok=False)

    fields = list(replayed[0])
    write_csv(output / "ebay_full_universe_migration.csv", replayed, fields)
    write_csv(
        output / "ebay_v2_v3_changed_listings.csv",
        [row for row in replayed if row["v2_v3_changed"] == "true"],
        fields,
    )
    write_csv(
        output / "ebay_migrated_classification_changes.csv",
        [row for row in replayed if row["classification_changed"] == "true"],
        fields,
    )
    write_csv(
        output / "ebay_migration_evidence_changes.csv",
        [row for row in replayed if row["evidence_changed"] == "true"],
        fields,
    )

    product_rows = [
        {
            "canonical_product_id": product_id,
            "canonical_product_name": product_names.get(product_id, ""),
            "accepted": counts.get("ACCEPTED", 0),
            "review": counts.get("REVIEW", 0),
            "rejected": counts.get("REJECTED", 0),
        }
        for product_id, counts in sorted(by_product.items())
    ]
    write_csv(
        output / "ebay_migration_product_summary.csv",
        product_rows,
        ["canonical_product_id", "canonical_product_name", "accepted", "review", "rejected"],
    )

    reason_rows = [
        {"reason_code": reason, "listing_count": count}
        for reason, count in _reason_counts(replayed, "precision_v3_exclusion_reasons").most_common()
    ]
    write_csv(
        output / "ebay_precision_v3_reason_summary.csv",
        reason_rows,
        ["reason_code", "listing_count"],
    )

    classification_changed = sum(row["classification_changed"] == "true" for row in replayed)
    v2_v3_changed = sum(row["v2_v3_changed"] == "true" for row in replayed)
    evidence_changed = sum(row["evidence_changed"] == "true" for row in replayed)
    row_count = len(replayed)
    summary = {
        "status": "PASS" if upgrade_count == 0 and v2_to_v3_upgrade_count == 0 else "FAIL",
        "mode": "FULL_UNIVERSE_PRODUCTION_MIGRATION",
        "quota_calls": 0,
        "baseline_matcher_version": BASELINE_MATCHER,
        "migration_matcher_version": MIGRATION_MATCHER,
        "migration_policy_mode": "downgrade_only",
        "source_file_count": len(listing_files),
        "listing_row_count": row_count,
        "unique_product_count": len(by_product),
        "classification_changed_row_count": classification_changed,
        "v2_v3_changed_row_count": v2_v3_changed,
        "evidence_changed_row_count": evidence_changed,
        "upgrade_transition_count": upgrade_count,
        "v2_to_v3_upgrade_transition_count": v2_to_v3_upgrade_count,
        "state_counts_saved": dict(sorted(state_saved.items())),
        "state_counts_precision_v2": dict(sorted(state_v2.items())),
        "state_counts_precision_v3": dict(sorted(state_v3.items())),
        "state_counts_migrated": dict(sorted(state_migrated.items())),
        "saved_to_v2_transitions": dict(sorted(saved_to_v2.items())),
        "v2_to_v3_transitions": dict(sorted(v2_to_v3.items())),
        "saved_to_migrated_transitions": dict(sorted(saved_to_migrated.items())),
        "saved_review_rate": round(state_saved.get("REVIEW", 0) / row_count, 6) if row_count else 0.0,
        "v3_review_rate": round(state_v3.get("REVIEW", 0) / row_count, 6) if row_count else 0.0,
        "saved_rejection_rate": round(state_saved.get("REJECTED", 0) / row_count, 6) if row_count else 0.0,
        "v3_rejection_rate": round(state_v3.get("REJECTED", 0) / row_count, 6) if row_count else 0.0,
        "output_root": str(output.resolve()),
    }
    (output / "ebay_full_universe_migration_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay all saved eBay evidence through precision-v2 and precision-v3-universal"
    )
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/operations/ebay_full_universe_migration"),
    )
    args = parser.parse_args()
    summary = run(args.input_root.resolve(), args.output_root.resolve())
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
