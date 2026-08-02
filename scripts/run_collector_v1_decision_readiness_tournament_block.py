from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_collector_v1_decision_readiness_tournament as builder
import certify_collector_v1_decision_readiness_tournament as certifier


def run_with_strict(module, strict: bool) -> int:
    original = sys.argv[:]
    try:
        sys.argv = [original[0]] + (["--strict"] if strict else [])
        return int(module.main())
    finally:
        sys.argv = original


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build_code = run_with_strict(builder, args.strict)
    if build_code != 0:
        print("Decision-readiness tournament failed; certification was not run.")
        return build_code

    certify_code = run_with_strict(certifier, args.strict)
    if certify_code != 0:
        print("Decision-readiness tournament certification failed.")
        return certify_code

    print("PASS_COLLECTOR_V1_DECISION_READINESS_TOURNAMENT_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
