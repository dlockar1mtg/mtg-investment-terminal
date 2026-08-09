from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts/build_precollector_horizon_specific_tournament_execution.py"
ARCHITECTURE_DIR = ROOT / "artifacts/precollector/horizon_specific_tournament_architecture"
CANONICAL_ARCHITECTURE = ARCHITECTURE_DIR / "precollector_horizon_specific_tournament_architecture.csv"
LEGACY_EXPECTED_ARCHITECTURE = ARCHITECTURE_DIR / "precollector_horizon_tournament_architecture.csv"


def discover_canonical_history() -> tuple[Path, pd.DataFrame, str, str, str]:
    id_names = [
        "canonical_product_id", "product_id", "canonical_id", "canonical_product_key",
        "tcgplayer_product_id", "tcgcsv_product_id",
    ]
    date_names = [
        "price_date", "observation_date", "date", "snapshot_date", "observed_at",
        "observation_timestamp", "price_timestamp", "as_of_date", "collected_at",
    ]
    price_names = [
        "market_price", "price", "governed_price", "historical_price",
        "canonical_price", "normalized_price", "marketprice",
    ]
    best: tuple[float, Path, pd.DataFrame, str, str, str] | None = None
    for path in (ROOT / "artifacts/precollector").rglob("*.csv"):
        try:
            frame = pd.read_csv(path, dtype=str).fillna("")
        except Exception:
            continue
        lower = {str(c).lower(): str(c) for c in frame.columns}
        id_col = next((lower[n] for n in id_names if n in lower), "")
        date_col = next((lower[n] for n in date_names if n in lower), "")
        price_col = next((lower[n] for n in price_names if n in lower), "")
        if not id_col:
            id_col = next((str(c) for c in frame.columns if "product" in str(c).lower() and "id" in str(c).lower()), "")
        if not date_col:
            date_col = next((str(c) for c in frame.columns if any(k in str(c).lower() for k in ["date", "timestamp", "observed", "collected"])), "")
        if not price_col:
            price_col = next((str(c) for c in frame.columns if "price" in str(c).lower() and not any(k in str(c).lower() for k in ["low", "high", "foil", "quantity"])), "")
        if not (id_col and date_col and price_col) or frame.empty:
            continue
        parsed_dates = pd.to_datetime(frame[date_col], errors="coerce", utc=True)
        parsed_prices = pd.to_numeric(frame[price_col], errors="coerce")
        valid = parsed_dates.notna() & parsed_prices.gt(0) & frame[id_col].astype(str).ne("")
        valid_rows = int(valid.sum())
        if valid_rows == 0:
            continue
        valid_ids = frame.loc[valid, id_col].astype(str)
        unique_ids = int(valid_ids.nunique())
        repeated_rows = valid_rows - unique_ids
        date_span_days = 0.0
        if valid_rows > 1:
            date_span_days = float((parsed_dates[valid].max() - parsed_dates[valid].min()).total_seconds() / 86400.0)
        score = valid_rows + repeated_rows * 5.0 + min(date_span_days, 3650.0)
        if repeated_rows <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, path, frame, id_col, date_col, price_col)
    if best is None:
        raise RuntimeError("CANONICAL_HISTORY_NOT_DISCOVERED_AFTER_SCHEMA_INFERENCE")
    return best[1], best[2], best[3], best[4], best[5]


def main() -> int:
    spec = importlib.util.spec_from_file_location("precollector_horizon_execution_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_HORIZON_EXECUTION_MODULE_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    original_run = module.run

    def corrected_run(command: list[str]) -> None:
        original_run(command)
        if CANONICAL_ARCHITECTURE.is_file():
            shutil.copy2(CANONICAL_ARCHITECTURE, LEGACY_EXPECTED_ARCHITECTURE)
        else:
            raise RuntimeError("CANONICAL_HORIZON_ARCHITECTURE_OUTPUT_MISSING")

    prior_snapshot_mode = os.environ.get("PRECOLLECTOR_USE_CERTIFIED_TCGCSV_SNAPSHOT")
    os.environ["PRECOLLECTOR_USE_CERTIFIED_TCGCSV_SNAPSHOT"] = "1"
    try:
        module.run = corrected_run
        module.discover_history = discover_canonical_history
        result = int(module.main())
    finally:
        if prior_snapshot_mode is None:
            os.environ.pop("PRECOLLECTOR_USE_CERTIFIED_TCGCSV_SNAPSHOT", None)
        else:
            os.environ["PRECOLLECTOR_USE_CERTIFIED_TCGCSV_SNAPSHOT"] = prior_snapshot_mode

    if result == 0:
        print("PASS_PRECOLLECTOR_HORIZON_EXECUTION_ARCHITECTURE_INTERFACE_CORRECTION_V1_1")
        print("PASS_PRECOLLECTOR_CANONICAL_HISTORY_SCHEMA_BINDING_V1_2")
        print("PASS_PRECOLLECTOR_CERTIFIED_SNAPSHOT_ONLY_REBUILD_V1_3")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
