from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_collector_v1_scarcity_v1a_and_experiments.py"
REGISTRY = ROOT / "config/mtg/governance/collector_v1_authoritative_data_registry.json"


def load_module():
    spec = importlib.util.spec_from_file_location("collector_v1_experiment_builder", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {BUILDER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    module = load_module()
    original_build_ssi = module.build_ssi_v1a
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    scarcity_path = ROOT / registry["authorities"]["scarcity_v1"]["path"]
    scarcity = pd.read_csv(scarcity_path, low_memory=False)
    scarcity["tcgplayer_product_id"] = module.normalize_id(scarcity["tcgplayer_product_id"])

    def governed_build_ssi(matrix: pd.DataFrame):
        m = matrix.copy()
        m["tcgplayer_product_id"] = module.normalize_id(m["tcgplayer_product_id"])
        raw_candidates = [
            "accepted_listing_count", "observable_listing_count", "listing_count",
            "review_listing_count", "review_count", "ambiguity_exclusion_count",
            "ambiguous_listing_count", "cross_product_ambiguity_count",
            "scarcity_confidence", "confidence_score", "scarcity_confidence_score",
        ]
        available = [c for c in raw_candidates if c in scarcity.columns]
        if not available:
            raise ValueError(f"Registered scarcity authority has no governed SSI V1A inputs; available={list(scarcity.columns)}")
        enriched = m.merge(
            scarcity[["tcgplayer_product_id"] + available].drop_duplicates("tcgplayer_product_id"),
            on="tcgplayer_product_id",
            how="left",
            suffixes=("", "_authority"),
        )
        for col in available:
            authority_col = f"{col}_authority"
            if authority_col in enriched.columns:
                enriched[col] = enriched[authority_col]
        result, diag = original_build_ssi(enriched)
        diag["raw_input_authority"] = registry["authorities"]["scarcity_v1"]["path"]
        diag["raw_input_columns"] = available
        return result, diag

    module.build_ssi_v1a = governed_build_ssi
    sys.argv = [str(BUILDER)] + (["--strict"] if args.strict else [])
    rc = int(module.main())
    if rc != 0:
        print("Collector V1 experiment foundation failed; baseline backtests were not run.")
        return rc

    command = [sys.executable, "scripts/run_collector_v1_routed_baseline_backtests.py"]
    if args.strict:
        command.append("--strict")
    rc = int(subprocess.run(command, cwd=ROOT, check=False).returncode)
    if rc == 0:
        print("PASS_COLLECTOR_V1_EXPERIMENT_AND_BASELINE_BLOCK")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
