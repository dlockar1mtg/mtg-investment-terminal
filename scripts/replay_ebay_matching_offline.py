from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision_v2 import identity_match_listing

STATE_RANK = {"REJECTED": 0, "REVIEW": 1, "ACCEPTED": 2}


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


def _clamp_downgrade_only(previous_state: str, candidate_state: str) -> str:
    previous = previous_state if previous_state in STATE_RANK else "REJECTED"
    candidate = candidate_state if candidate_state in STATE_RANK else "REJECTED"
    return candidate if STATE_RANK[candidate] <= STATE_RANK[previous] else previous


def replay_row(row: dict[str, str]) -> dict[str, object]:
    product = product_from_row(row)
    item = {
        "itemId": row.get("ebay_item_id", ""),
        "title": row.get("title", ""),
        "itemWebUrl": row.get("item_url", ""),
        "price": {"value": row.get("price", "0") or "0", "currency": row.get("currency", "USD") or "USD"},
        "condition": row.get("condition", ""),
    }
    result = identity_match_listing(
        product,
        item,
        row.get("source_run_id", "OFFLINE-REPLAY"),
        row.get("observed_at_utc", ""),
    )

    previous_state = row.get("match_state", "")
    final_state = _clamp_downgrade_only(previous_state, result.match_state)
    reasons = [value for value in result.exclusion_reasons.split("|") if value]
    if final_state != result.match_state:
        reasons.append("offline_upgrade_blocked")

    previous_score_text = str(row.get("match_score", ""))
    try:
        previous_score = float(previous_score_text)
    except (TypeError, ValueError):
        previous_score = 0.0
    final_score = min(previous_score, result.match_score) if final_state == previous_state else result.match_score

    updated: dict[str, object] = dict(row)
    updated["previous_match_score"] = previous_score_text
    updated["previous_match_state"] = previous_state
    updated["previous_exclusion_reasons"] = row.get("exclusion_reasons", "")
    updated["match_score"] = round(final_score, 4)
    updated["match_state"] = final_state
    updated["exclusion_reasons"] = "|".join(dict.fromkeys(reasons))
    updated["classification_changed"] = str(previous_state != final_state).lower()
    updated["evidence_changed"] = str(
        previous_score_text != str(updated["match_score"])
        or row.get("exclusion_reasons", "") != updated["exclusion_reasons"]
    ).lower()
    return updated


def run(input_root: Path, output_root: Path) -> dict[str, object]:
    listing_files = sorted(input_root.rglob("ebay_listing_match_results_*.csv"))
    if not listing_files:
        raise FileNotFoundError(f"No eBay listing evidence found under {input_root}")

    source_rows: list[dict[str, str]] = []
    for path in listing_files:
        for row in read_csv(path):
            row = dict(row)
            row["offline_source_file"] = str(path.resolve())
            source_rows.append(row)

    replayed = [replay_row(row) for row in source_rows]
    state_before = Counter(row.get("match_state", "") for row in source_rows)
    state_after = Counter(str(row.get("match_state", "")) for row in replayed)
    transitions = Counter(
        f"{old.get('match_state', '')}->{new.get('match_state', '')}"
        for old, new in zip(source_rows, replayed)
    )
    upgrades = sum(
        STATE_RANK.get(str(new.get("match_state", "")), -1)
        > STATE_RANK.get(str(old.get("match_state", "")), -1)
        for old, new in zip(source_rows, replayed)
    )

    by_product: dict[str, Counter[str]] = defaultdict(Counter)
    product_names: dict[str, str] = {}
    for row in replayed:
        product_id = str(row.get("canonical_product_id", ""))
        product_names.setdefault(product_id, str(row.get("canonical_product_name", "")))
        by_product[product_id][str(row.get("match_state", ""))] += 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = output_root / f"replay_{stamp}"
    output.mkdir(parents=True, exist_ok=False)

    fields = list(replayed[0])
    write_csv(output / "ebay_offline_reclassified_listings.csv", replayed, fields)
    write_csv(
        output / "ebay_offline_changed_listings.csv",
        [row for row in replayed if row["classification_changed"] == "true"],
        fields,
    )
    write_csv(
        output / "ebay_offline_evidence_changes.csv",
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
        output / "ebay_offline_product_summary.csv",
        product_rows,
        ["canonical_product_id", "canonical_product_name", "accepted", "review", "rejected"],
    )

    classification_changed = sum(row["classification_changed"] == "true" for row in replayed)
    evidence_changed = sum(row["evidence_changed"] == "true" for row in replayed)
    summary = {
        "status": "PASS" if upgrades == 0 else "FAILED",
        "mode": "OFFLINE_REPLAY",
        "quota_calls": 0,
        "source_file_count": len(listing_files),
        "listing_row_count": len(replayed),
        "unique_product_count": len(by_product),
        "classification_changed_row_count": classification_changed,
        "evidence_changed_row_count": evidence_changed,
        "upgrade_transition_count": upgrades,
        "state_counts_before": dict(sorted(state_before.items())),
        "state_counts_after": dict(sorted(state_after.items())),
        "transitions": dict(sorted(transitions.items())),
        "output_root": str(output.resolve()),
    }
    (output / "ebay_offline_replay_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay saved eBay listing evidence without API calls")
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/operations/ebay_offline_replay"))
    args = parser.parse_args()
    summary = run(args.input_root.resolve(), args.output_root.resolve())
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
