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
    return subprocess.run(command, cwd=ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build_code = run("run_collector_v1_product_level_forecast_ranking_tournament.py", args.strict)
    if build_code != 0:
        print("Product-level forecast and ranking tournament did not satisfy all gates; certification was not run.")
        return build_code

    cert_code = run("certify_collector_v1_product_level_forecast_ranking_tournament.py", args.strict)
    if cert_code == 0:
        print("PASS_COLLECTOR_V1_PRODUCT_LEVEL_FORECAST_RANKING_TOURNAMENT_BLOCK")
    return cert_code


if __name__ == "__main__":
    raise SystemExit(main())
