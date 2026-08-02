from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    runner = load_module(
        ROOT / "scripts/run_collector_v1_final_purchase_adequacy_tournament.py",
        "collector_final_purchase_adequacy_runner",
    )

    # Normalize the fixed comparison date to UTC so it is compatible with
    # timezone-aware latest_price_date values parsed from the governed data.
    runner.AS_OF_DATE = pd.Timestamp("2026-08-01", tz="UTC")

    run_code = int(runner.main())
    if run_code != 0:
        return run_code

    certifier = load_module(
        ROOT / "scripts/certify_collector_v1_final_purchase_adequacy_tournament.py",
        "collector_final_purchase_adequacy_certifier",
    )
    cert_code = int(certifier.main())
    if cert_code == 0:
        print("PASS_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_TIMEZONE_REMEDIATION_BLOCK")
    return cert_code


if __name__ == "__main__":
    raise SystemExit(main())
