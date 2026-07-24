from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.collector_box_admission import build_admission_ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    result = build_admission_ledger(args.profile, args.output_root)
    print("PHASE 10.7.4 COLLECTOR BOX ADMISSION: COMPLETE")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
