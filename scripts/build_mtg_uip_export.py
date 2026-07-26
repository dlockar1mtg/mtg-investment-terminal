from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.integration.uip_export import write_mtg_uip_export


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the governed MTG domain export consumed by UIP")
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--purchase-plan", type=Path, required=True)
    parser.add_argument("--purchase-summary", type=Path, required=True)
    parser.add_argument("--holdings", type=Path, required=True)
    parser.add_argument("--carry-forward", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = write_mtg_uip_export(
        args.output,
        decisions_path=args.decisions,
        purchase_plan_path=args.purchase_plan,
        purchase_summary_path=args.purchase_summary,
        holdings_path=args.holdings,
        carry_forward_path=args.carry_forward,
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("domain_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
