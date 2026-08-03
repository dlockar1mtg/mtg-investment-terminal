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

    build_code = run("build_collector_v1_early_coverage_adjudication.py", args.strict)
    if build_code != 0:
        print("Early coverage adjudication build failed; certification was not run.")
        return build_code

    cert_code = run("certify_collector_v1_early_coverage_adjudication.py", args.strict)
    if cert_code != 0:
        print("Early coverage adjudication certification failed.")
        return cert_code

    print("PASS_COLLECTOR_V1_EARLY_COVERAGE_ADJUDICATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
