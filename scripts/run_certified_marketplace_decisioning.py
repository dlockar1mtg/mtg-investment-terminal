from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.marketplace_decisioning import write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build MTG decisions from certified marketplace prices")
    parser.add_argument("--certified-observations", type=Path, required=True)
    parser.add_argument("--model-input", type=Path, required=True)
    parser.add_argument("--consolidated-output", type=Path, required=True)
    parser.add_argument("--decisions-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    missing = [
        str(path.resolve())
        for path in (args.certified_observations, args.model_input)
        if not path.is_file()
    ]
    if missing:
        payload = {
            "status": "FAILED",
            "missing_inputs": missing,
            "reason_codes": ["CERTIFIED_MARKETPLACE_DECISIONING_INPUT_NOT_AVAILABLE"],
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    payload = write_outputs(
        args.certified_observations.resolve(),
        args.model_input.resolve(),
        args.consolidated_output.resolve(),
        args.decisions_output.resolve(),
        args.summary_output.resolve(),
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
