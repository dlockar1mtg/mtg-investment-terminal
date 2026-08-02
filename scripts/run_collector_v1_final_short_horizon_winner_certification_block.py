from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, strict: bool) -> int:
    command = [sys.executable, str(ROOT / "scripts" / script)]
    if strict:
        command.append("--strict")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cohort_code = run("certify_collector_v1_early_cohort_fallback_tournament.py", args.strict)
    if cohort_code != 0:
        print("Early cohort fallback certification failed; final winner manifest was not built.")
        return cohort_code

    build_code = run("build_collector_v1_final_short_horizon_winner_manifest.py", args.strict)
    if build_code != 0:
        print("Final short-horizon winner manifest build failed; certification was not run.")
        return build_code

    certify_code = run("certify_collector_v1_final_short_horizon_winner_manifest.py", args.strict)
    if certify_code != 0:
        print("Final short-horizon winner certification failed.")
        return certify_code

    print("PASS_COLLECTOR_V1_FINAL_SHORT_HORIZON_WINNER_CERTIFICATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
