from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/validation/phase_10/collector_booster_boxes/governed_registry/collector_booster_box_governed_registry.csv"
MASTER = ROOT / "data/product_master/product_master_model_input.csv"
CANONICAL = ROOT / "data/operations/collector_early_lifecycle_universe/candidate_v1_0_0/collector_early_lifecycle_canonical_universe.csv"
FORECASTS = ROOT / "data/operations/collector_early_lifecycle_forecast_engine/candidate_v1_0_0/collector_early_lifecycle_complete_universe.csv"


def clean_id(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def id_set(df: pd.DataFrame, aliases: list[str]) -> set[str]:
    for column in aliases:
        if column in df.columns:
            return {clean_id(x) for x in df[column] if clean_id(x)}
    return set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    paths = [
        (MASTER, "product_master"),
        (REGISTRY, "registry"),
        (CANONICAL, "canonical_universe"),
        (FORECASTS, "forecast_universe"),
    ]
    for path, label in paths:
        if not path.exists():
            failures.append(f"missing_{label}")

    master = pd.read_csv(MASTER, dtype=str, keep_default_na=False, low_memory=False) if MASTER.exists() else pd.DataFrame()
    registry = pd.read_csv(REGISTRY, dtype=str, keep_default_na=False) if REGISTRY.exists() else pd.DataFrame()
    canonical = pd.read_csv(CANONICAL, dtype=str, keep_default_na=False) if CANONICAL.exists() else pd.DataFrame()
    forecasts = pd.read_csv(FORECASTS, dtype=str, keep_default_na=False) if FORECASTS.exists() else pd.DataFrame()

    collector_master = master.loc[
        master.get("box_name", pd.Series(dtype=str)).astype(str).str.contains("Collector Booster", case=False, na=False)
    ].copy() if not master.empty else pd.DataFrame()

    master_ids = id_set(collector_master, ["tcgplayer_product_id", "product_key"])
    registry_ids = id_set(registry, ["tcgplayer_product_id", "canonical_product_id"])
    canonical_ids = id_set(canonical, ["tcgplayer_product_id", "product_key"])
    forecast_ids = id_set(forecasts, ["product_key", "tcgplayer_product_id"])

    if not master_ids:
        failures.append("collector_master_identity_set_empty")
    if master_ids - registry_ids:
        failures.append("master_products_missing_from_registry:" + "|".join(sorted(master_ids - registry_ids)))
    if registry_ids - canonical_ids:
        failures.append("registry_products_missing_from_canonical:" + "|".join(sorted(registry_ids - canonical_ids)))
    if canonical_ids - forecast_ids:
        failures.append("canonical_products_missing_from_forecasts:" + "|".join(sorted(canonical_ids - forecast_ids)))
    if forecast_ids - canonical_ids:
        failures.append("forecast_products_not_in_canonical:" + "|".join(sorted(forecast_ids - canonical_ids)))

    if not registry.empty:
        registry_normalized = registry["tcgplayer_product_id"].map(clean_id)
        if registry_normalized.duplicated().any():
            failures.append("duplicate_registry_tcgplayer_ids")
        if registry["canonical_product_name"].duplicated().any():
            failures.append("duplicate_registry_names")

    if not canonical.empty:
        if "tcgplayer_product_id" not in canonical.columns:
            failures.append("canonical_tcgplayer_identity_column_missing")
        else:
            canonical_tcg = canonical["tcgplayer_product_id"].map(clean_id)
            canonical_key = canonical["product_key"].map(clean_id)
            if canonical_tcg.isin(["", "NOT_AVAILABLE"]).any():
                failures.append("canonical_tcgplayer_identity_missing")
            if not canonical_key.equals(canonical_tcg):
                mismatch_ids = canonical.loc[canonical_key != canonical_tcg, "product_key"].map(clean_id).tolist()
                failures.append("canonical_product_key_not_tcgplayer_identity:" + "|".join(mismatch_ids))
            if canonical_key.duplicated().any():
                failures.append("duplicate_canonical_product_ids")
        if canonical["product_name"].duplicated().any():
            failures.append("duplicate_canonical_product_names")

    if not forecasts.empty:
        forecast_keys = forecasts["product_key"].map(clean_id)
        if forecast_keys.duplicated().any():
            failures.append("duplicate_forecast_product_ids")
        if forecasts["product_name"].duplicated().any():
            failures.append("duplicate_forecast_products")
        if forecasts["forecast_center_365"].isin(["", "NOT_AVAILABLE"]).any():
            failures.append("missing_forecast_centers")
        if (forecasts["forecast_status"] == "BLOCKED").any():
            failures.append("blocked_products_detected")

    result = {
        "audit_name": "Collector Dynamic Registry and Forecast Alignment Audit",
        "audit_version": "2.1.0",
        "dynamic_count_policy": True,
        "identity_contract": "TCGPLAYER_PRODUCT_ID_PRIMARY",
        "product_master_collector_count": int(len(master_ids)),
        "registry_count": int(len(registry_ids)),
        "canonical_universe_count": int(len(canonical_ids)),
        "forecast_universe_count": int(len(forecast_ids)),
        "master_registry_coverage_complete": not bool(master_ids - registry_ids),
        "registry_canonical_coverage_complete": not bool(registry_ids - canonical_ids),
        "canonical_forecast_set_equal": canonical_ids == forecast_ids,
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
