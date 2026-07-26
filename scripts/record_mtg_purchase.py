from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.portfolio.operations import record_purchase


def main() -> int:
    parser = argparse.ArgumentParser(description="Record an executed MTG purchase and update holdings")
    parser.add_argument("--holdings", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--investment-product-id", required=True)
    parser.add_argument("--quantity", type=float, required=True)
    parser.add_argument("--unit-price", type=float, required=True)
    parser.add_argument("--transaction-date")
    parser.add_argument("--transaction-id")
    parser.add_argument("--source", default="MANUAL")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    payload = record_purchase(
        args.holdings,
        args.ledger,
        investment_product_id=args.investment_product_id,
        quantity=args.quantity,
        unit_price=args.unit_price,
        transaction_date=args.transaction_date,
        transaction_id=args.transaction_id,
        source=args.source,
        notes=args.notes,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
