from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "scripts/run_precollector_long_horizon_monte_carlo_execution.py"

HISTORY_DATE_ALIASES = (
    "observed_at",
    "observation_date",
    "observed_date",
    "price_date",
    "history_date",
    "snapshot_date",
    "effective_date",
    "recorded_at",
    "collected_at",
    "source_date",
    "observation_timestamp",
    "timestamp",
    "as_of_date",
    "date",
)


def load_engine():
    spec = importlib.util.spec_from_file_location("precollector_long_horizon_monte_carlo_engine", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("MONTE_CARLO_ENGINE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_history_date_column(frame: pd.DataFrame) -> str | None:
    columns = list(frame.columns)
    for name in HISTORY_DATE_ALIASES:
        if name in columns:
            return name

    date_like = [
        name
        for name in columns
        if any(token in name.lower() for token in ("date", "time", "observed", "snapshot", "effective", "recorded", "collected"))
    ]
    viable: list[tuple[float, str]] = []
    for name in date_like:
        parsed = pd.to_datetime(frame[name], errors="coerce", utc=True)
        ratio = float(parsed.notna().mean()) if len(frame) else 0.0
        if ratio >= 0.80:
            viable.append((ratio, name))
    if not viable:
        return None
    viable.sort(key=lambda item: (-item[0], item[1]))
    return viable[0][1]


def normalize_authority_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns = set(frame.columns)
    has_product = bool(columns & {"tcgplayer_product_id", "product_id", "investment_product_id"})
    has_price = bool(columns & {"price", "market_price", "observed_price", "current_price"})
    is_foundation = bool(columns & {"forecast_route", "forecast_method"})
    if not has_product or not has_price or is_foundation:
        return frame

    resolved = resolve_history_date_column(frame)
    if resolved is None:
        raise RuntimeError(f"CANONICAL_HISTORY_DATE_COLUMN_UNRESOLVED:columns={list(frame.columns)}")
    if resolved == "observed_at":
        return frame
    return frame.rename(columns={resolved: "observed_at"})


def main() -> int:
    engine = load_engine()
    original_read_csv = engine.pd.read_csv

    def governed_read_csv(*args: Any, **kwargs: Any) -> pd.DataFrame:
        frame = original_read_csv(*args, **kwargs)
        return normalize_authority_frame(frame)

    engine.pd.read_csv = governed_read_csv
    return int(engine.main())


if __name__ == "__main__":
    raise SystemExit(main())
