from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(replay_root: Path) -> dict[str, object]:
    changed_path = replay_root / "ebay_offline_changed_listings.csv"
    if not changed_path.is_file():
        raise FileNotFoundError(changed_path)

    rows = read_csv(changed_path)
    downgrades = [
        row for row in rows
        if row.get("previous_match_state") != row.get("match_state")
    ]

    reason_counts: Counter[str] = Counter()
    transition_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    pack_count_candidates: list[dict[str, object]] = []

    for row in downgrades:
        transition = f"{row.get('previous_match_state', '')}->{row.get('match_state', '')}"
        transition_counts[transition] += 1
        class_counts[row.get("product_class", "UNKNOWN")] += 1
        reasons = [value for value in row.get("exclusion_reasons", "").split("|") if value]
        reason_counts.update(reasons)

        title = row.get("title", "")
        if (
            "BOOSTER" in row.get("product_class", "").upper()
            and row.get("previous_match_state") == "ACCEPTED"
            and row.get("match_state") == "REJECTED"
            and any(f" {count} pack" in f" {title.lower()}" for count in (4, 12, 24, 30, 36))
        ):
            pack_count_candidates.append({
                "canonical_product_id": row.get("canonical_product_id", ""),
                "canonical_product_name": row.get("canonical_product_name", ""),
                "title": title,
                "previous_match_state": row.get("previous_match_state", ""),
                "match_state": row.get("match_state", ""),
                "exclusion_reasons": row.get("exclusion_reasons", ""),
            })

    reason_rows = [
        {"reason": reason, "count": count}
        for reason, count in reason_counts.most_common()
    ]
    transition_rows = [
        {"transition": transition, "count": count}
        for transition, count in transition_counts.most_common()
    ]
    class_rows = [
        {"product_class": product_class, "count": count}
        for product_class, count in class_counts.most_common()
    ]

    write_csv(replay_root / "ebay_downgrade_reason_counts.csv", reason_rows, ["reason", "count"])
    write_csv(replay_root / "ebay_downgrade_transition_counts.csv", transition_rows, ["transition", "count"])
    write_csv(replay_root / "ebay_downgrade_product_class_counts.csv", class_rows, ["product_class", "count"])
    write_csv(
        replay_root / "ebay_booster_pack_count_downgrade_candidates.csv",
        pack_count_candidates,
        [
            "canonical_product_id",
            "canonical_product_name",
            "title",
            "previous_match_state",
            "match_state",
            "exclusion_reasons",
        ],
    )

    summary = {
        "status": "PASS",
        "mode": "OFFLINE_DOWNGRADE_AUDIT",
        "quota_calls": 0,
        "downgrade_count": len(downgrades),
        "pack_count_candidate_count": len(pack_count_candidates),
        "transition_counts": dict(transition_counts),
        "product_class_counts": dict(class_counts),
        "top_reasons": reason_rows[:25],
    }
    (replay_root / "ebay_offline_downgrade_audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit offline eBay classification downgrades")
    parser.add_argument("--replay-root", type=Path, required=True)
    args = parser.parse_args()
    run(args.replay_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
