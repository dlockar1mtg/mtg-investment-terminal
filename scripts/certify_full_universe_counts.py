"""Certify the governed full-marketplace universe summary.

The weekly job used to require exact counts (234 displays, 1,227 products), so approving one
new product failed every run. This checks what must always hold instead:
- the totals add up (displays + Secret Lairs = products; TCGCSV-ready + eBay-only = products);
- every product is eBay-ready;
- no class has shrunk sharply below the last certified baseline (a broken source, not a retirement).
Growth is fine.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

SUMMARY = Path("data/operations/mtg_full_marketplace/full_product_map_summary.json")

# Last certified counts (Sep 2026). A drop of more than MAX_DROP below these means a source broke.
BASELINE = {"booster_display_count": 234, "secret_lair_count": 993, "total_marketplace_products": 1227}
MAX_DROP = 0.05


def check(payload: dict) -> list[str]:
    errors: list[str] = []
    keys = ("booster_display_count", "secret_lair_count", "total_marketplace_products",
            "ebay_ready_count", "tcgcsv_ready_count", "ebay_only_count")
    missing = [k for k in keys if not isinstance(payload.get(k), int)]
    if missing:
        return [f"missing or non-integer: {', '.join(missing)}"]
    total = payload["total_marketplace_products"]
    if payload["booster_display_count"] + payload["secret_lair_count"] != total:
        errors.append(f"displays {payload['booster_display_count']} + Secret Lairs {payload['secret_lair_count']} != products {total}")
    if payload["ebay_ready_count"] != total:
        errors.append(f"eBay-ready {payload['ebay_ready_count']} != products {total}")
    if payload["tcgcsv_ready_count"] + payload["ebay_only_count"] != total:
        errors.append(f"TCGCSV-ready {payload['tcgcsv_ready_count']} + eBay-only {payload['ebay_only_count']} != products {total}")
    for key, base in BASELINE.items():
        floor = int(base * (1 - MAX_DROP))
        if payload[key] < floor:
            errors.append(f"{key} {payload[key]} is below {floor} (baseline {base} minus {int(MAX_DROP * 100)}%)")
    return errors


def main(path: Path = SUMMARY) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = check(payload)
    if errors:
        print("Governed universe check failed:\n" + "\n".join(errors), file=sys.stderr)
        return 1
    changes = {k: payload[k] - v for k, v in BASELINE.items() if payload[k] != v}
    print(json.dumps({**payload, "change_vs_baseline": changes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else SUMMARY))
