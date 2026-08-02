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

    build_rc = run("run_collector_v1_expanded_endpoint_route_tournament.py", args.strict)
    if build_rc != 0:
        print("Expanded endpoint-route tournament build failed; certification was not run.")
        return build_rc

    certify_rc = run("certify_collector_v1_expanded_endpoint_route_tournament.py", args.strict)
    if certify_rc != 0:
        print("Expanded endpoint-route tournament certification failed.")
        return certify_rc

    print("PASS_COLLECTOR_V1_EXPANDED_TOURNAMENT_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
