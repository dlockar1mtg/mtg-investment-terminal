from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_collector_v1_authoritative_feature_foundation.py"
CERTIFIER = ROOT / "scripts/certify_collector_v1_authoritative_feature_foundation.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("collector_v1_authoritative_feature_builder", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load builder: {BUILDER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    builder = load_builder()
    original_first_column = builder.first_column

    def governed_first_column(df, names, required=True):
        governed_names = list(names)
        # The registered safe-monthly authority certifies its observed price as
        # source_market_price. This is an explicit schema alias, not fallback
        # discovery and does not mutate the source artifact.
        if any(name in governed_names for name in [
            "market_price", "price", "monthly_market_price", "tcg_market_price", "value"
        ]):
            governed_names.append("source_market_price")
        return original_first_column(df, governed_names, required=required)

    builder.first_column = governed_first_column
    sys.argv = [str(BUILDER)] + (["--strict"] if args.strict else [])
    build_code = int(builder.main())
    if build_code != 0:
        print("Authoritative feature build failed; certification was not run.")
        return build_code

    command = [sys.executable, str(CERTIFIER)]
    if args.strict:
        command.append("--strict")
    cert = subprocess.run(command, cwd=ROOT, check=False)
    return int(cert.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
