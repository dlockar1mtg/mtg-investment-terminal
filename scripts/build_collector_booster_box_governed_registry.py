from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from terminal2.registry.collector_booster_boxes import build_governed_registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-one", type=Path, required=True)
    parser.add_argument("--batch-two", type=Path, required=True)
    parser.add_argument("--batch-one-coverage", type=Path, required=True)
    parser.add_argument("--batch-two-coverage", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    result = build_governed_registry(
        batch_one_path=args.batch_one,
        batch_two_path=args.batch_two,
        batch_one_coverage_path=args.batch_one_coverage,
        batch_two_coverage_path=args.batch_two_coverage,
        output_root=args.output_root,
    )
    print("PHASE 10.7.2 COLLECTOR BOX REGISTRY: COMPLETE")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
