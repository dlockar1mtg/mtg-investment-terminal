from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts/run_collector_v1_expanded_endpoint_route_tournament.py"
CERTIFY_SCRIPT = ROOT / "scripts/certify_collector_v1_expanded_endpoint_route_tournament.py"
EARLY_PATH = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation/collector_v1_early_opportunity_predictions.csv"


def load_build_module():
    spec = importlib.util.spec_from_file_location("collector_v1_expanded_tournament_build", BUILD_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load governed build script: {BUILD_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight_early_schema(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Registered early-opportunity predictions are missing: {path}")
    frame = pd.read_csv(path, nrows=5)
    required = {
        "tcgplayer_product_id",
        "age_months",
        "model_variant",
        "predicted_first_year_return",
    }
    missing = sorted(required - set(frame.columns))
    actual_aliases = [
        "actual_return_365d_from_release",
        "actual_first_year_return",
        "first_year_return",
        "actual_return",
    ]
    actual_column = next((name for name in actual_aliases if name in frame.columns), None)
    if missing or actual_column is None:
        raise ValueError(
            "Expanded tournament early schema preflight failed. "
            f"missing_required={missing}; actual_return_alias={actual_column}; "
            f"available={list(frame.columns)}"
        )
    return {
        "path": str(path.relative_to(ROOT)),
        "required_columns_present": True,
        "actual_return_source_column": actual_column,
        "canonical_actual_return_column": "actual_first_year_return",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    preflight = preflight_early_schema(EARLY_PATH)
    print(json.dumps({"expanded_tournament_schema_preflight": preflight}, indent=2))

    module = load_build_module()
    original = module.calibrate_early_predictions

    def governed_calibrate_early_predictions(frame: pd.DataFrame) -> pd.DataFrame:
        work = frame.copy()
        if "actual_first_year_return" not in work.columns:
            if "actual_return_365d_from_release" in work.columns:
                work["actual_first_year_return"] = work["actual_return_365d_from_release"]
            elif "first_year_return" in work.columns:
                work["actual_first_year_return"] = work["first_year_return"]
            elif "actual_return" in work.columns:
                work["actual_first_year_return"] = work["actual_return"]
            else:
                raise ValueError(
                    "No governed realized first-year return column is available; "
                    f"available={list(work.columns)}"
                )
        return original(work)

    module.calibrate_early_predictions = governed_calibrate_early_predictions

    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(BUILD_SCRIPT)] + (["--strict"] if args.strict else [])
        build_code = int(module.main())
    finally:
        sys.argv = saved_argv

    if build_code != 0:
        print("Expanded endpoint-route tournament build failed; certification was not run.")
        return build_code

    certify_cmd = [sys.executable, str(CERTIFY_SCRIPT)]
    if args.strict:
        certify_cmd.append("--strict")
    certification = subprocess.run(certify_cmd, cwd=ROOT, check=False)
    if certification.returncode != 0:
        print("Expanded endpoint-route tournament certification failed.")
        return int(certification.returncode)

    print("PASS_COLLECTOR_V1_EXPANDED_TOURNAMENT_BLOCK_V2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
