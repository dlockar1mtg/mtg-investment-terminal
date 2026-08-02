from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_collector_v1_authoritative_feature_foundation.py"
ADJUDICATOR = ROOT / "scripts/adjudicate_collector_v1_authoritative_feature_foundation.py"
CERTIFIER = ROOT / "scripts/certify_collector_v1_authoritative_feature_foundation.py"
MATRIX = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_foundation/collector_v1_authoritative_feature_matrix.csv"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_builder() -> int:
    builder = load_module("collector_v1_authoritative_feature_builder", BUILDER)
    original_first_column = builder.first_column

    def governed_first_column(df, names, required=True):
        governed_names = list(names)
        if any(name in governed_names for name in [
            "market_price", "price", "monthly_market_price", "tcg_market_price", "value"
        ]):
            governed_names.append("source_market_price")
        return original_first_column(df, governed_names, required=required)

    builder.first_column = governed_first_column
    sys.argv = [str(BUILDER)]
    return int(builder.main())


def run_adjudicator(strict: bool) -> int:
    adjudicator = load_module("collector_v1_authoritative_feature_adjudicator", ADJUDICATOR)
    original_read_csv = adjudicator.pd.read_csv

    def governed_read_csv(path, *args, **kwargs):
        frame = original_read_csv(path, *args, **kwargs)
        try:
            resolved = Path(path).resolve()
        except TypeError:
            return frame
        if resolved == MATRIX.resolve() and "tcgplayer_product_id" in frame.columns:
            frame["tcgplayer_product_id"] = (
                frame["tcgplayer_product_id"]
                .astype("string")
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )
        return frame

    adjudicator.pd.read_csv = governed_read_csv
    sys.argv = [str(ADJUDICATOR)] + (["--strict"] if strict else [])
    return int(adjudicator.main())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build_rc = run_builder()
    if not MATRIX.exists():
        print("Authoritative feature build did not emit the required intermediate matrix.")
        return build_rc or 1

    adjudicate_rc = run_adjudicator(args.strict)
    if adjudicate_rc != 0:
        print("Authoritative feature adjudication failed; final certification was not run.")
        return adjudicate_rc

    command = [sys.executable, str(CERTIFIER)]
    if args.strict:
        command.append("--strict")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
