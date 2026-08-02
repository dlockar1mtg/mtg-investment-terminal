from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPANDED_DIR = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_pre_recommendation_tournament_foundation"
BUILDER_PATH = ROOT / "scripts/build_collector_v1_pre_recommendation_tournament_foundation.py"
CERTIFIER_PATH = ROOT / "scripts/certify_collector_v1_pre_recommendation_tournament_foundation.py"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify_csv(path: Path) -> dict:
    frame = pd.read_csv(path, nrows=5)
    cols = {str(c).lower() for c in frame.columns}
    name = path.name.lower()

    prediction_markers = {
        "prediction", "predicted", "actual", "actual_value", "actual_price",
        "prediction_bias_corrected", "horizon_days", "tournament_lane",
    }
    candidate_markers = {
        "model_variant", "promotion_status", "promotable", "selection_score",
        "mae", "rmse", "bias", "rank_correlation", "horizon_days",
    }

    prediction_score = sum(1 for marker in prediction_markers if marker in cols)
    candidate_score = sum(1 for marker in candidate_markers if marker in cols)

    if "prediction" in name or "predictions" in name or "backtest" in name:
        prediction_score += 3
    if "metric" in name or "candidate" in name or "winner" in name:
        candidate_score += 2

    return {
        "path": path,
        "rows": sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore")) - 1,
        "columns": sorted(cols),
        "prediction_score": prediction_score,
        "candidate_score": candidate_score,
    }


def select_unique(records: list[dict], role: str) -> Path:
    score_key = "prediction_score" if role == "expanded_predictions" else "candidate_score"
    ranked = sorted(records, key=lambda item: (item[score_key], item["rows"]), reverse=True)
    if not ranked or ranked[0][score_key] < 3:
        raise RuntimeError(f"No schema-valid {role} authority found in {EXPANDED_DIR}")
    if len(ranked) > 1 and ranked[0][score_key] == ranked[1][score_key] and ranked[0]["rows"] == ranked[1]["rows"]:
        raise RuntimeError(
            f"Ambiguous {role} authorities: {ranked[0]['path'].name}, {ranked[1]['path'].name}"
        )
    return ranked[0]["path"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if not EXPANDED_DIR.exists():
        raise FileNotFoundError(f"Certified expanded tournament directory missing: {EXPANDED_DIR}")

    records = [classify_csv(path) for path in sorted(EXPANDED_DIR.glob("*.csv"))]
    prediction_path = select_unique(records, "expanded_predictions")
    candidate_path = select_unique(records, "expanded_candidates")

    if prediction_path == candidate_path:
        alternatives = [r for r in records if r["path"] != prediction_path and r["candidate_score"] >= 3]
        if not alternatives:
            raise RuntimeError("Prediction and candidate authorities resolved to the same file with no valid alternative")
        candidate_path = sorted(alternatives, key=lambda item: (item["candidate_score"], item["rows"]), reverse=True)[0]["path"]

    preflight = {
        "expanded_authority_schema_preflight": {
            "bounded_directory": str(EXPANDED_DIR.relative_to(ROOT)),
            "csv_files_examined": len(records),
            "resolved_expanded_predictions": str(prediction_path.relative_to(ROOT)),
            "resolved_expanded_predictions_sha256": sha256(prediction_path),
            "resolved_expanded_candidates": str(candidate_path.relative_to(ROOT)),
            "resolved_expanded_candidates_sha256": sha256(candidate_path),
            "recursive_repository_discovery_used": False,
            "certified_source_files_mutated": False,
        }
    }
    print(json.dumps(preflight, indent=2))

    builder = load_module(BUILDER_PATH, "collector_pre_recommendation_foundation_builder")
    call_count = {"value": 0}

    def resolved_first_existing(paths: list[Path]) -> Path | None:
        call_count["value"] += 1
        return prediction_path if call_count["value"] == 1 else candidate_path

    builder.first_existing = resolved_first_existing
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(BUILDER_PATH)] + (["--strict"] if args.strict else [])
        build_code = int(builder.main())
    finally:
        sys.argv = original_argv

    if build_code != 0:
        print("Pre-recommendation tournament foundation V2 build failed; certification was not run.")
        return build_code

    certifier = load_module(CERTIFIER_PATH, "collector_pre_recommendation_foundation_certifier")
    try:
        sys.argv = [str(CERTIFIER_PATH)] + (["--strict"] if args.strict else [])
        certify_code = int(certifier.main())
    finally:
        sys.argv = original_argv

    if certify_code != 0:
        print("Pre-recommendation tournament foundation V2 certification failed.")
        return certify_code

    print("PASS_COLLECTOR_V1_PRE_RECOMMENDATION_TOURNAMENT_FOUNDATION_BLOCK_V2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
