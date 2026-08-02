from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURE_PATH = ROOT / "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix.csv"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_current_product_application_foundation"

ID_ALIASES = ["tcgplayer_product_id", "product_id", "sealed_product_id", "id"]
NAME_ALIASES = ["product_name", "name", "sealed_product_name"]
PRICE_ALIASES = [
    "current_price", "latest_price", "market_price", "tcgplayer_market_price",
    "price", "current_market_price", "latest_market_price", "cutoff_price",
    "price_at_cutoff", "release_anchor_price",
]
DATE_ALIASES = [
    "price_date", "observation_date", "as_of_date", "snapshot_date", "cutoff_date",
    "latest_price_date", "date",
]
ROUTE_ALIASES = [
    "route", "forecast_route", "assigned_route", "resolved_route", "tournament_lane",
    "forecast_method",
]
HISTORY_ALIASES = ["history_months", "history_months_available", "months_of_history", "history_months_at_cutoff"]
AGE_ALIASES = ["age_months", "product_age_months", "months_since_release"]

GOVERNED_ROUTES = {
    "COMPARABLE_PRODUCT_ADJUSTED",
    "DIRECT_HISTORY_CALIBRATED",
    "DIRECT_HISTORY_LIMITED",
    "EARLY_OPPORTUNITY_COHORT_FALLBACK",
}


def first_existing(columns: list[str], aliases: list[str]) -> str | None:
    lookup = {c.lower(): c for c in columns}
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    return None


def bool_series(frame: pd.DataFrame, aliases: list[str]) -> pd.Series | None:
    col = first_existing(list(frame.columns), aliases)
    if col is None:
        return None
    raw = frame[col]
    if pd.api.types.is_bool_dtype(raw):
        return raw.fillna(False)
    text = raw.astype(str).str.strip().str.lower()
    return text.isin({"true", "1", "yes", "y", "eligible", "pass"})


def normalize_route(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    aliases = {
        "COMPARABLE": "COMPARABLE_PRODUCT_ADJUSTED",
        "COMPARABLE_PRODUCT": "COMPARABLE_PRODUCT_ADJUSTED",
        "DIRECT_HISTORY": "DIRECT_HISTORY_CALIBRATED",
        "DIRECT": "DIRECT_HISTORY_CALIBRATED",
        "LIMITED": "DIRECT_HISTORY_LIMITED",
        "EARLY": "EARLY_OPPORTUNITY_COHORT_FALLBACK",
        "EARLY_OPPORTUNITY": "EARLY_OPPORTUNITY_COHORT_FALLBACK",
    }
    return aliases.get(text, text if text in GOVERNED_ROUTES else None)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def derive_routes(frame: pd.DataFrame) -> tuple[pd.Series, dict]:
    columns = list(frame.columns)
    explicit_col = first_existing(columns, ROUTE_ALIASES)
    diagnostics: dict = {"explicit_route_column": explicit_col}
    if explicit_col:
        routes = frame[explicit_col].map(normalize_route)
        diagnostics["route_derivation"] = "explicit_governed_route_column"
        return routes, diagnostics

    early = bool_series(frame, [
        "early_opportunity_eligible", "early_detector_eligible", "early_cohort_eligible",
        "early_opportunity_cohort_eligible",
    ])
    calibrated = bool_series(frame, [
        "direct_history_calibrated_eligible", "calibrated_history_eligible",
        "direct_calibrated_eligible",
    ])
    limited = bool_series(frame, [
        "direct_history_limited_eligible", "limited_history_eligible", "direct_limited_eligible",
    ])
    direct = bool_series(frame, ["direct_history_eligible", "direct_eligible"])
    comparable = bool_series(frame, ["comparable_eligible", "comparable_product_eligible"])

    history_col = first_existing(columns, HISTORY_ALIASES)
    age_col = first_existing(columns, AGE_ALIASES)
    history = pd.to_numeric(frame[history_col], errors="coerce") if history_col else pd.Series(np.nan, index=frame.index)
    age = pd.to_numeric(frame[age_col], errors="coerce") if age_col else pd.Series(np.nan, index=frame.index)

    routes = pd.Series(index=frame.index, dtype="object")
    if early is not None:
        early_mask = early & (age.le(12) if age_col else True)
        routes.loc[early_mask] = "EARLY_OPPORTUNITY_COHORT_FALLBACK"
    if calibrated is not None:
        routes.loc[routes.isna() & calibrated] = "DIRECT_HISTORY_CALIBRATED"
    if limited is not None:
        routes.loc[routes.isna() & limited] = "DIRECT_HISTORY_LIMITED"
    if direct is not None:
        if history_col:
            routes.loc[routes.isna() & direct & history.ge(24)] = "DIRECT_HISTORY_CALIBRATED"
            routes.loc[routes.isna() & direct & history.lt(24)] = "DIRECT_HISTORY_LIMITED"
        else:
            routes.loc[routes.isna() & direct] = "DIRECT_HISTORY_CALIBRATED"
    if comparable is not None:
        routes.loc[routes.isna() & comparable] = "COMPARABLE_PRODUCT_ADJUSTED"

    diagnostics.update({
        "route_derivation": "certified_eligibility_precedence",
        "history_column": history_col,
        "age_column": age_col,
        "early_eligibility_present": early is not None,
        "calibrated_eligibility_present": calibrated is not None,
        "limited_eligibility_present": limited is not None,
        "direct_eligibility_present": direct is not None,
        "comparable_eligibility_present": comparable is not None,
    })
    return routes, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not FEATURE_PATH.exists():
        raise FileNotFoundError(FEATURE_PATH)

    frame = pd.read_csv(FEATURE_PATH)
    columns = list(frame.columns)
    id_col = first_existing(columns, ID_ALIASES)
    name_col = first_existing(columns, NAME_ALIASES)
    price_col = first_existing(columns, PRICE_ALIASES)
    date_col = first_existing(columns, DATE_ALIASES)

    if id_col is None or name_col is None:
        raise RuntimeError(f"Feature matrix missing product identity columns. available={columns}")

    universe = frame[[id_col, name_col]].copy()
    universe.columns = ["tcgplayer_product_id", "product_name"]
    universe = universe.drop_duplicates("tcgplayer_product_id")
    universe.to_csv(OUT_DIR / "collector_v1_normalized_product_universe_authority.csv", index=False)

    price_ready = False
    if price_col is not None:
        price = frame[[id_col, name_col, price_col] + ([date_col] if date_col else [])].copy()
        rename = {id_col: "tcgplayer_product_id", name_col: "product_name", price_col: "latest_price"}
        if date_col:
            rename[date_col] = "observation_date"
        price = price.rename(columns=rename)
        price["latest_price"] = pd.to_numeric(price["latest_price"], errors="coerce")
        price_ready = bool((price["latest_price"] > 0).all())
        price.to_csv(OUT_DIR / "collector_v1_normalized_latest_price_authority.csv", index=False)

    routes, route_diag = derive_routes(frame)
    route = universe.copy()
    route_map = pd.DataFrame({"tcgplayer_product_id": frame[id_col], "assigned_route": routes})
    route = route.merge(route_map.drop_duplicates("tcgplayer_product_id"), on="tcgplayer_product_id", how="left")
    route_ready = bool(route["assigned_route"].notna().all() and set(route["assigned_route"].dropna()).issubset(GOVERNED_ROUTES))
    route.to_csv(OUT_DIR / "collector_v1_normalized_route_assignment_authority.csv", index=False)

    diagnostics = {
        "feature_matrix": str(FEATURE_PATH.relative_to(ROOT)),
        "feature_matrix_rows": int(len(frame)),
        "feature_matrix_columns": columns,
        "id_column": id_col,
        "name_column": name_col,
        "price_column": price_col,
        "date_column": date_col,
        "price_authority_ready": price_ready,
        "route_authority_ready": route_ready,
        "unresolved_route_products": route.loc[route["assigned_route"].isna(), ["tcgplayer_product_id", "product_name"]].to_dict("records"),
        "route_counts": route["assigned_route"].fillna("UNRESOLVED").value_counts().to_dict(),
        **route_diag,
        "certified_source_files_mutated": False,
        "normalized_authorities_written": True,
    }
    (OUT_DIR / "collector_v1_current_product_lineage_resolution_v2.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    print(json.dumps({"current_product_lineage_resolution_v2": diagnostics}, indent=2))

    if not price_ready or not route_ready or len(universe) != 50:
        return 1 if args.strict else 0

    builder = load_module(ROOT / "scripts/build_collector_v1_current_product_application_foundation.py", "product_foundation_builder")
    build_code = int(builder.main())
    if build_code != 0:
        return build_code
    certifier = load_module(ROOT / "scripts/certify_collector_v1_current_product_application_foundation.py", "product_foundation_certifier")
    cert_code = int(certifier.main())
    if cert_code == 0:
        print("PASS_COLLECTOR_V1_CURRENT_PRODUCT_APPLICATION_FOUNDATION_BLOCK_V2")
    return cert_code


if __name__ == "__main__":
    raise SystemExit(main())
