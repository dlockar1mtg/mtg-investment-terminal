from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EXPANDED_PATH = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament/collector_v1_expanded_price_predictions.csv"
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

    builder = load_module(SCRIPTS / "run_collector_v1_residual_interval_tournament.py", "collector_residual_interval_builder_v4")
    certifier = load_module(SCRIPTS / "certify_collector_v1_residual_interval_tournament.py", "collector_residual_interval_certifier_v4")

    expanded = pd.read_csv(EXPANDED_PATH)
    expanded_required = {
        "tcgplayer_product_id", "forecast_method", "horizon_days",
        "predicted_price_bias_corrected", "actual_future_price", "model_variant",
    }
    expanded_missing = sorted(expanded_required - set(expanded.columns))
    if expanded_missing:
        raise ValueError(f"Certified expanded authority missing required columns: {expanded_missing}; available={list(expanded.columns)}")

    cohort = pd.read_csv(COHORT_PATH)
    cohort_required = {
        "tcgplayer_product_id", "age_months", "actual_return_365d_from_release",
        "model_variant", "predicted_first_year_return",
    }
    cohort_missing = sorted(cohort_required - set(cohort.columns))
    if cohort_missing:
        raise ValueError(f"Certified cohort authority missing required columns: {cohort_missing}; available={list(cohort.columns)}")

    original_read_csv = pd.read_csv

    def patched_read_csv(filepath_or_buffer, *read_args, **read_kwargs):
        frame = original_read_csv(filepath_or_buffer, *read_args, **read_kwargs)
        try:
            resolved = Path(filepath_or_buffer).resolve()
        except (TypeError, OSError):
            return frame

        if resolved == EXPANDED_PATH.resolve():
            frame = frame.copy()
            frame["tournament_lane"] = frame["forecast_method"]
            frame["prediction_corrected"] = frame["predicted_price_bias_corrected"]
            frame["actual_value"] = frame["actual_future_price"]
            if "cutoff_month" in frame.columns and "cutoff_date" not in frame.columns:
                frame["cutoff_date"] = frame["cutoff_month"]
        elif resolved == COHORT_PATH.resolve():
            frame = frame.copy()
            frame["predicted_return"] = frame["predicted_first_year_return"]
        return frame

    pd.read_csv = patched_read_csv
    builder.pd.read_csv = patched_read_csv

    print(json.dumps({
        "residual_interval_combined_schema_preflight": {
            "expanded_authority": str(EXPANDED_PATH.relative_to(ROOT)),
            "expanded_route_mapping": "forecast_method -> tournament_lane",
            "expanded_prediction_mapping": "predicted_price_bias_corrected -> prediction_corrected",
            "expanded_actual_mapping": "actual_future_price -> actual_value",
            "cohort_authority": str(COHORT_PATH.relative_to(ROOT)),
            "cohort_prediction_mapping": "predicted_first_year_return -> predicted_return",
            "cohort_actual_column": "actual_return_365d_from_release",
            "schema_aliases_applied_in_memory": True,
            "bias_corrected_prediction_precedence": True,
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

    print("PASS_COLLECTOR_V1_RESIDUAL_INTERVAL_TOURNAMENT_BLOCK_V4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
