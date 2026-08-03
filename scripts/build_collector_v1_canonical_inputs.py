"""Build immutable-source-derived canonical inputs for Collector V1 modeling."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_canonical_inputs"
ROUTES = ROOT / "data/operations/collector_forecast_method_routing/candidate_v1_0_0/collector_forecast_method_routes.csv"
MODEL = ROOT / "data/product_master/product_master_model_input.csv"
HISTORY = ROOT / "data/operations/mtg_history_foundation/universal_mtg_price_history.csv"


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def norm(value: object) -> str:
    text = str(value or "").strip().removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_present(frame: pd.DataFrame, names: list[str]) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [str(path) for path in (ROUTES, MODEL, HISTORY) if not path.is_file()]
    if missing:
        print(json.dumps({"status": "FAIL_REQUIRED_INPUTS_MISSING", "missing": missing}, indent=2))
        return 1 if args.strict else 0

    routes = load(ROUTES)
    model = load(MODEL)
    history = load(HISTORY)

    route_key = first_present(routes, ["investment_product_id", "product_id"])
    model_key = first_present(model, ["investment_product_id", "product_id"])
    model_tcg = first_present(model, ["tcgplayer_product_id", "resolved_tcgplayer_product_id"])
    if not route_key or not model_key or not model_tcg:
        raise RuntimeError(f"Cannot build route crosswalk. route_columns={list(routes.columns)} model_columns={list(model.columns)}")

    crosswalk_cols = [model_key, model_tcg]
    for optional in ["product_name", "box_name", "approved_product_name", "release_date"]:
        if optional in model.columns and optional not in crosswalk_cols:
            crosswalk_cols.append(optional)
    crosswalk = model[crosswalk_cols].copy()
    crosswalk[model_key] = crosswalk[model_key].map(str).str.strip()
    crosswalk[model_tcg] = crosswalk[model_tcg].map(norm)
    crosswalk = crosswalk[crosswalk[model_key].ne("")].drop_duplicates(subset=[model_key], keep="first")

    canonical_routes = routes.merge(crosswalk, left_on=route_key, right_on=model_key, how="left", suffixes=("", "_model"))
    canonical_routes["tcgplayer_product_id"] = canonical_routes[model_tcg].map(norm)
    route_unmapped = canonical_routes[canonical_routes["tcgplayer_product_id"].eq("")].copy()
    canonical_routes.to_csv(OUT / "collector_v1_canonical_forecast_routes.csv", index=False)
    route_unmapped.to_csv(OUT / "collector_v1_unmapped_forecast_routes.csv", index=False)

    history_id = first_present(history, ["tcgplayer_product_id", "resolved_tcgplayer_product_id", "product_id"])
    history_date = first_present(history, ["observation_date", "date", "price_date", "snapshot_date", "as_of_date", "observed_at"])
    history_price = first_present(history, ["market_price", "price", "value", "market", "median_price", "low_price"])
    if not history_id or not history_date or not history_price:
        raise RuntimeError(f"Cannot build canonical history. columns={list(history.columns)}")

    working = history.copy()
    working["tcgplayer_product_id"] = working[history_id].map(norm)
    working["observation_timestamp_utc"] = pd.to_datetime(working[history_date], errors="coerce", utc=True)
    working["observation_date_utc"] = working["observation_timestamp_utc"].dt.strftime("%Y-%m-%d")
    working["market_price_numeric"] = pd.to_numeric(working[history_price], errors="coerce")

    blank_id_rows = working[working["tcgplayer_product_id"].eq("")].copy()
    invalid_date_rows = working[working["observation_timestamp_utc"].isna()].copy()
    invalid_price_rows = working[working["market_price_numeric"].isna() | working["market_price_numeric"].le(0)].copy()
    eligible = working[
        working["tcgplayer_product_id"].ne("")
        & working["observation_timestamp_utc"].notna()
        & working["market_price_numeric"].gt(0)
    ].copy()

    source_col = first_present(eligible, ["source", "source_name", "provider", "marketplace"])
    grain_cols = ["tcgplayer_product_id", "observation_date_utc"]
    grouped = eligible.groupby(grain_cols, dropna=False)
    canonical_history = grouped.agg(
        market_price=("market_price_numeric", "median"),
        market_price_min=("market_price_numeric", "min"),
        market_price_max=("market_price_numeric", "max"),
        source_row_count=("market_price_numeric", "size"),
        first_observed_at=("observation_timestamp_utc", "min"),
        last_observed_at=("observation_timestamp_utc", "max"),
    ).reset_index()
    if source_col:
        source_counts = grouped[source_col].nunique().reset_index(name="source_count")
        canonical_history = canonical_history.merge(source_counts, on=grain_cols, how="left")
    else:
        canonical_history["source_count"] = 0
    canonical_history["price_dispersion"] = canonical_history["market_price_max"] - canonical_history["market_price_min"]
    canonical_history.to_csv(OUT / "collector_v1_canonical_daily_price_history.csv", index=False)

    duplicate_source_rows = int(eligible.duplicated(subset=grain_cols, keep=False).sum())
    summary = {
        "block_name": "Collector V1 Canonical Inputs",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_route_rows": int(len(routes)),
        "canonical_route_rows": int(len(canonical_routes)),
        "mapped_route_rows": int(canonical_routes["tcgplayer_product_id"].ne("").sum()),
        "unmapped_route_rows": int(len(route_unmapped)),
        "unique_route_tcgplayer_ids": int(canonical_routes["tcgplayer_product_id"].replace("", pd.NA).nunique()),
        "source_history_rows": int(len(history)),
        "blank_history_id_rows": int(len(blank_id_rows)),
        "invalid_history_date_rows": int(len(invalid_date_rows)),
        "invalid_or_nonpositive_history_price_rows": int(len(invalid_price_rows)),
        "eligible_history_source_rows": int(len(eligible)),
        "duplicate_source_rows_at_product_day_grain": duplicate_source_rows,
        "canonical_product_day_rows": int(len(canonical_history)),
        "canonical_history_product_count": int(canonical_history["tcgplayer_product_id"].nunique()),
        "history_grain_contract": "ONE_ROW_PER_TCGPLAYER_PRODUCT_ID_PER_UTC_DATE_USING_MEDIAN_VALID_MARKET_PRICE",
        "source_history_mutated": False,
        "artifact_hashes": {
            "routes": sha256(ROUTES),
            "model": sha256(MODEL),
            "history": sha256(HISTORY),
            "canonical_routes": sha256(OUT / "collector_v1_canonical_forecast_routes.csv"),
            "canonical_history": sha256(OUT / "collector_v1_canonical_daily_price_history.csv"),
        },
        "status": "PASS_COLLECTOR_V1_CANONICAL_INPUTS_READY" if len(route_unmapped) == 0 and len(canonical_history) > 0 else "FAIL_COLLECTOR_V1_CANONICAL_INPUTS",
    }
    (OUT / "collector_v1_canonical_inputs_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"].startswith("PASS") else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
