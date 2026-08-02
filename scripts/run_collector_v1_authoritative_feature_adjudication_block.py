from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT)
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    # Run compatibility builder without strict gating. It may report known pre-adjudication blockers,
    # but it must still emit the governed intermediate artifacts.
    build_rc = run([sys.executable, "scripts/run_collector_v1_authoritative_feature_foundation_block.py"])
    required = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_foundation/collector_v1_authoritative_feature_matrix.csv"
    if not required.exists():
        print("Authoritative feature build did not emit the required intermediate matrix.")
        return build_rc or 1

    adjudicate_cmd = [sys.executable, "scripts/adjudicate_collector_v1_authoritative_feature_foundation.py"]
    if args.strict:
        adjudicate_cmd.append("--strict")
    adjudicate_rc = run(adjudicate_cmd)
    if adjudicate_rc != 0:
        print("Authoritative feature adjudication failed; final certification was not run.")
        return adjudicate_rc

    certify_cmd = [sys.executable, "scripts/certify_collector_v1_authoritative_feature_foundation.py"]
    if args.strict:
        certify_cmd.append("--strict")
    return run(certify_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
