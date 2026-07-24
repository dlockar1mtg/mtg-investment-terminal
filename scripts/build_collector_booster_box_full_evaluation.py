from __future__ import annotations

import argparse
import json
from pathlib import Path

from terminal2.market_sources.collector_box_evaluation import build_evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission-ledger", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_evaluation(args.admission_ledger, args.output_root)
    print("PHASE 10.7.5 COLLECTOR BOX EVALUATION: COMPLETE")
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["status"] == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
