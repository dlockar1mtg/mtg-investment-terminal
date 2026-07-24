from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.registry.pre_collector_booster_boxes import build_governed_registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--collector-registry", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_governed_registry(
        args.candidate,
        args.collector_registry,
        args.output_root,
    )
    print("PHASE 10.8.2 PRE-COLLECTOR REGISTRY: COMPLETE")
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["status"] == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
