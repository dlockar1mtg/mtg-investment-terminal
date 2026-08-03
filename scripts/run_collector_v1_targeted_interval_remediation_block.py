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

    build_code = run("run_collector_v1_targeted_interval_remediation.py", args.strict)
    if build_code != 0:
        print("Targeted interval remediation did not resolve the final blocked cell; certification was not run.")
        return build_code

    certify_code = run("certify_collector_v1_targeted_interval_remediation.py", args.strict)
    if certify_code != 0:
        print("Targeted interval remediation certification failed.")
        return certify_code

    print("PASS_COLLECTOR_V1_TARGETED_INTERVAL_REMEDIATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
