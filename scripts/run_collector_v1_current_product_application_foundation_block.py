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

    build_code = run("build_collector_v1_current_product_application_foundation.py", args.strict)
    if build_code != 0:
        print("Current-product application foundation did not resolve all required authorities; certification was not run.")
        return build_code

    cert_code = run("certify_collector_v1_current_product_application_foundation.py", args.strict)
    if cert_code != 0:
        print("Current-product application foundation certification failed.")
        return cert_code

    print("PASS_COLLECTOR_V1_CURRENT_PRODUCT_APPLICATION_FOUNDATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
