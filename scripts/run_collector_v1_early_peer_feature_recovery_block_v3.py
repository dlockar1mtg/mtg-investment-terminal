from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V2_PATH = ROOT / "scripts/run_collector_v1_early_peer_feature_recovery_block_v2.py"
OUTCOME_FILE = "collector_v1_first_year_outcomes.csv"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    original_read_csv = pd.read_csv
    preflight: dict[str, object] = {
        "outcome_authority_filename": OUTCOME_FILE,
        "source_actual_return_column": None,
        "canonical_actual_return_column": "actual_return_365d_from_release",
        "schema_alias_applied_in_memory": False,
        "certified_source_files_mutated": False,
    }

    def read_csv_with_outcome_alias(*read_args, **read_kwargs):
        frame = original_read_csv(*read_args, **read_kwargs)
        source = read_args[0] if read_args else read_kwargs.get("filepath_or_buffer")
        source_name = Path(str(source)).name if source is not None else ""
        if source_name == OUTCOME_FILE:
            candidates = [
                "actual_return_365d_from_release",
                "first_year_return",
                "return_365d_from_release",
                "return_365d",
            ]
            selected = next((name for name in candidates if name in frame.columns), None)
            preflight["source_actual_return_column"] = selected
            if selected is None:
                raise ValueError(
                    "Certified first-year outcome authority has no recognized realized-return column. "
                    f"available={list(frame.columns)}"
                )
            if "actual_return_365d_from_release" not in frame.columns:
                frame = frame.copy()
                frame["actual_return_365d_from_release"] = frame[selected]
                preflight["schema_alias_applied_in_memory"] = True
        return frame

    pd.read_csv = read_csv_with_outcome_alias
    try:
        v2 = load_module(V2_PATH)
        import sys
        previous_argv = sys.argv[:]
        sys.argv = [str(V2_PATH)] + (["--strict"] if args.strict else [])
        try:
            result = int(v2.main())
        finally:
            sys.argv = previous_argv
    finally:
        pd.read_csv = original_read_csv

    print(json.dumps({"early_peer_feature_recovery_outcome_schema_preflight": preflight}, indent=2))
    if result == 0:
        print("PASS_COLLECTOR_V1_EARLY_PEER_FEATURE_RECOVERY_BLOCK_V3")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
