from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.delivery.governed_loader import activate_delivery

DELIVERY = ROOT / "data/operations/mtg_terminal_delivery"
ACTIVE = ROOT / "data/warehouse/current/governed_terminal"
STATE = ROOT / "data/operations/mtg_terminal_activation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-root", type=Path, default=DELIVERY)
    parser.add_argument("--active-root", type=Path, default=ACTIVE)
    parser.add_argument("--state-root", type=Path, default=STATE)
    args = parser.parse_args()

    result = activate_delivery(
        args.delivery_root.resolve(),
        args.active_root.resolve(),
        args.state_root.resolve(),
    )
    print(json.dumps(result.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
