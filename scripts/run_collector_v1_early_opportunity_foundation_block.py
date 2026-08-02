from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build = [sys.executable, "scripts/build_collector_v1_early_opportunity_foundation.py"]
    if args.strict:
        build.append("--strict")
    build_rc = run(build)
    if build_rc != 0:
        print("Early-opportunity foundation build failed; certification was not run.")
        return build_rc

    certify = [sys.executable, "scripts/certify_collector_v1_early_opportunity_foundation.py"]
    if args.strict:
        certify.append("--strict")
    cert_rc = run(certify)
    if cert_rc == 0:
        print("PASS_COLLECTOR_V1_EARLY_OPPORTUNITY_FOUNDATION_BLOCK")
    return cert_rc


if __name__ == "__main__":
    raise SystemExit(main())
