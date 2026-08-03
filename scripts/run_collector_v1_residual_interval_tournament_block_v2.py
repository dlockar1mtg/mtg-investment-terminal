from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EXPANDED_PATH = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament/collector_v1_expanded_price_predictions.csv"
BUILDER_PATH = SCRIPTS / "run_collector_v1_residual_interval_tournament.py"
CERTIFIER_PATH = SCRIPTS / "certify_collector_v1_residual_interval_tournament.py"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("collector_residual_interval_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    header = pd.read_csv(EXPANDED_PATH, nrows=0)
    required_source = {
        "forecast_method",
        "horizon_days",
        "predicted_price_bias_corrected",
        "actual_future_price",
    }
    missing = sorted(required_source - set(header.columns))
    if missing:
        raise RuntimeError(f"Expanded prediction schema missing required source columns: {missing}")

    preflight = {
        "residual_interval_schema_preflight": {
            "expanded_authority": str(EXPANDED_PATH.relative_to(ROOT)),
            "route_source_column": "forecast_method",
            "route_canonical_column": "tournament_lane",
            "prediction_source_column": "predicted_price_bias_corrected",
            "prediction_canonical_column": "prediction_corrected",
            "actual_source_column": "actual_future_price",
            "actual_canonical_column": "actual_value",
            "schema_aliases_applied_in_memory": True,
            "bias_corrected_prediction_precedence": True,
            "certified_source_files_mutated": False,
        }
    }
    print(json.dumps(preflight, indent=2))

    builder = load_module(BUILDER_PATH)
    original_read_csv = builder.pd.read_csv

    def patched_read_csv(path, *a, **kw):
        frame = original_read_csv(path, *a, **kw)
        try:
            resolved = Path(path).resolve()
        except TypeError:
            return frame
        if resolved == EXPANDED_PATH.resolve():
            frame = frame.copy()
            aliases = {
                "forecast_method": "tournament_lane",
                "predicted_price_bias_corrected": "prediction_corrected",
                "actual_future_price": "actual_value",
                "cutoff_month": "cutoff_date",
            }
            for source, canonical in aliases.items():
                if source in frame.columns and canonical not in frame.columns:
                    frame[canonical] = frame[source]
        return frame

    builder.pd.read_csv = patched_read_csv
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(BUILDER_PATH)] + (["--strict"] if args.strict else [])
        build_code = int(builder.main())
    finally:
        sys.argv = original_argv
        builder.pd.read_csv = original_read_csv

    if build_code != 0:
        print("Residual interval tournament build did not fully resolve all winner cells; certification was not run.")
        return build_code

    cert_cmd = [sys.executable, str(CERTIFIER_PATH)]
    if args.strict:
        cert_cmd.append("--strict")
    cert_code = subprocess.run(cert_cmd, cwd=ROOT, check=False).returncode
    if cert_code != 0:
        print("Residual interval tournament certification failed.")
        return cert_code

    print("PASS_COLLECTOR_V1_RESIDUAL_INTERVAL_TOURNAMENT_BLOCK_V2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
