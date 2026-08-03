from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
COHORT_PATH = ROOT / "data/governance/permanence/certification/collector_v1_early_cohort_fallback_tournament/collector_v1_early_cohort_fallback_predictions.csv"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    builder = load_module(SCRIPTS / "run_collector_v1_residual_interval_tournament.py", "collector_residual_interval_builder_v3")
    certifier = load_module(SCRIPTS / "certify_collector_v1_residual_interval_tournament.py", "collector_residual_interval_certifier_v3")

    cohort = pd.read_csv(COHORT_PATH)
    required = {
        "tcgplayer_product_id",
        "age_months",
        "actual_return_365d_from_release",
        "model_variant",
        "predicted_first_year_return",
    }
    missing = sorted(required - set(cohort.columns))
    if missing:
        raise ValueError(f"Certified cohort prediction authority missing required columns: {missing}; available={list(cohort.columns)}")

    original_read_csv = pd.read_csv

    def patched_read_csv(filepath_or_buffer, *read_args, **read_kwargs):
        frame = original_read_csv(filepath_or_buffer, *read_args, **read_kwargs)
        try:
            resolved = Path(filepath_or_buffer).resolve()
        except (TypeError, OSError):
            return frame

        if resolved == COHORT_PATH.resolve():
            frame = frame.copy()
            frame["predicted_return"] = frame["predicted_first_year_return"]
        return frame

    pd.read_csv = patched_read_csv
    builder.pd.read_csv = patched_read_csv

    print(json.dumps({
        "residual_interval_cohort_schema_preflight": {
            "cohort_authority": str(COHORT_PATH.relative_to(ROOT)),
            "prediction_source_column": "predicted_first_year_return",
            "prediction_canonical_column": "predicted_return",
            "actual_source_column": "actual_return_365d_from_release",
            "schema_alias_applied_in_memory": True,
            "certified_source_files_mutated": False,
        }
    }, indent=2))

    import sys
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(SCRIPTS / "run_collector_v1_residual_interval_tournament.py")]
        if args.strict:
            sys.argv.append("--strict")
        build_code = int(builder.main())
    finally:
        sys.argv = original_argv
        pd.read_csv = original_read_csv

    if build_code != 0:
        print("Residual interval tournament build did not fully resolve all winner cells; certification was not run.")
        return build_code

    try:
        sys.argv = [str(SCRIPTS / "certify_collector_v1_residual_interval_tournament.py")]
        if args.strict:
            sys.argv.append("--strict")
        cert_code = int(certifier.main())
    finally:
        sys.argv = original_argv

    if cert_code != 0:
        print("Residual interval tournament certification failed.")
        return cert_code

    print("PASS_COLLECTOR_V1_RESIDUAL_INTERVAL_TOURNAMENT_BLOCK_V3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
