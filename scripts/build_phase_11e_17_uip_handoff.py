from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.delivery.uip_handoff import build_uip_handoff

DELIVERY = ROOT / "data/operations/mtg_terminal_delivery"
HANDOFF = ROOT / "data/operations/mtg_uip_handoff"


def main() -> int:
    payload = build_uip_handoff(ROOT, DELIVERY, HANDOFF)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
