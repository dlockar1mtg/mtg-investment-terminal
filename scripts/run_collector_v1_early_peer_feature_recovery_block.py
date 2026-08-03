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
    return subprocess.run(cmd, cwd=ROOT).returncode


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    build = run("build_collector_v1_early_peer_feature_recovery.py", args.strict)
    if build != 0:
        print("Early peer feature recovery build failed; certification was not run.")
        return build
    certify = run("certify_collector_v1_early_peer_feature_recovery.py", args.strict)
    if certify != 0:
        print("Early peer feature recovery certification failed.")
        return certify
    print("PASS_COLLECTOR_V1_EARLY_PEER_FEATURE_RECOVERY_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
