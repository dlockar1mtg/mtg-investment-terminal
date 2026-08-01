from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/validation/phase_10/collector_booster_boxes/governed_registry/collector_booster_box_governed_registry.csv"
CANONICAL = ROOT / "data/operations/collector_early_lifecycle_universe/candidate_v1_0_0/collector_early_lifecycle_canonical_universe.csv"
FORECASTS = ROOT / "data/operations/collector_early_lifecycle_forecast_engine/candidate_v1_0_0/collector_early_lifecycle_complete_universe.csv"
EXPECTED_IDS = {"706142", "628315"}


def clean_id(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    for path, label in [(REGISTRY, "registry"), (CANONICAL, "canonical_universe"), (FORECASTS, "forecast_universe")]:
        if not path.exists():
            failures.append(f"missing_{label}")

    registry = pd.read_csv(REGISTRY, dtype=str, keep_default_na=False) if REGISTRY.exists() else pd.DataFrame()
    canonical = pd.read_csv(CANONICAL, dtype=str, keep_default_na=False) if CANONICAL.exists() else pd.DataFrame()
    forecasts = pd.read_csv(FORECASTS, dtype=str, keep_default_na=False) if FORECASTS.exists() else pd.DataFrame()

    if len(registry) != 51:
        failures.append(f"registry_count_not_51:{len(registry)}")
    if len(canonical) != 51:
        failures.append(f"canonical_count_not_51:{len(canonical)}")
    if len(forecasts) != 51:
        failures.append(f"forecast_count_not_51:{len(forecasts)}")

    if not registry.empty:
        ids = set(registry["tcgplayer_product_id"].map(clean_id)) if "tcgplayer_product_id" in registry else set()
        if not EXPECTED_IDS.issubset(ids):
            failures.append("reconciled_ids_missing")
        if registry["tcgplayer_product_id"].map(clean_id).duplicated().any():
            failures.append("duplicate_registry_tcgplayer_ids")
        if registry["canonical_product_name"].duplicated().any():
            failures.append("duplicate_registry_names")

    if not canonical.empty and "source_lineage" in canonical:
        multi_source_count = int(canonical["source_lineage"].str.contains("\\|", regex=True).sum())
        if multi_source_count != 51:
            failures.append(f"canonical_multi_source_lineage_not_51:{multi_source_count}")

    if not forecasts.empty:
        if forecasts["product_name"].duplicated().any():
            failures.append("duplicate_forecast_products")
        if forecasts["forecast_center_365"].isin(["", "NOT_AVAILABLE"]).any():
            failures.append("missing_forecast_centers")
        if (forecasts["forecast_status"] == "BLOCKED").any():
            failures.append("blocked_products_detected")

    result = {
        "audit_name": "Collector Registry and Forecast Universe Alignment Audit",
        "audit_version": "1.0.0",
        "registry_count": int(len(registry)),
        "canonical_universe_count": int(len(canonical)),
        "forecast_universe_count": int(len(forecasts)),
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
