from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.marketplace_quality import certify_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify normalized MTG marketplace observations")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()

    if not args.input.is_file():
        payload = {
            "status": "FAILED",
            "reason_codes": ["NORMALIZED_MARKETPLACE_OBSERVATIONS_NOT_AVAILABLE"],
            "input_path": str(args.input.resolve()),
        }
        exit_code = 1
    else:
        payload = certify_file(args.input.resolve(), args.output.resolve())
        payload["reason_codes"] = ["MARKETPLACE_OBSERVATION_CERTIFICATION_COMPLETED"]
        exit_code = 0 if payload["status"] == "PASS" else 2

    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
