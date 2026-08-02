from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/run_collector_v1_targeted_long_horizon_method_remediation.py"
CERTIFY = ROOT / "scripts/certify_collector_v1_targeted_long_horizon_method_remediation.py"


def run(script: Path, strict: bool) -> int:
    command = [sys.executable, str(script)]
    if strict:
        command.append("--strict")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build_code = run(BUILD, args.strict)
    if build_code != 0:
        print("Targeted long-horizon method remediation did not resolve all routes; certification was not run.")
        return build_code

    certify_code = run(CERTIFY, args.strict)
    if certify_code != 0:
        print("Targeted long-horizon method remediation certification failed.")
        return certify_code

    print("PASS_COLLECTOR_V1_TARGETED_LONG_HORIZON_METHOD_REMEDIATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
