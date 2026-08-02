from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, strict: bool) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script)]
    if strict:
        cmd.append("--strict")
    return int(subprocess.run(cmd, cwd=ROOT, check=False).returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build = run("run_collector_v1_early_cohort_fallback_tournament.py", args.strict)
    if build != 0:
        print("Early cohort fallback tournament build failed; certification was not run.")
        return build
    certify = run("certify_collector_v1_early_cohort_fallback_tournament.py", args.strict)
    if certify != 0:
        print("Early cohort fallback tournament certification failed.")
        return certify
    print("PASS_COLLECTOR_V1_EARLY_COHORT_FALLBACK_TOURNAMENT_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
