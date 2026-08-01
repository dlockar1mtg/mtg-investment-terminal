from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_early_lifecycle_universe/candidate_v1_0_0"
SOURCES = [
    ROOT / "data/product_master/product_master_model_input.csv",
    ROOT / "data/validation/phase_10/collector_booster_boxes/governed_registry/collector_booster_box_governed_registry.csv",
]


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def norm(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    text = re.sub(r"\bcollector booster (display|box)\b", "collector booster", text)
    return " ".join(text.split())


def choose_by_alias(df: pd.DataFrame, aliases: list[str]) -> str | None:
    cols = {str(c).lower(): str(c) for c in df.columns}
    return next((cols[a.lower()] for a in aliases if a.lower() in cols), None)


def choose_name_column(df: pd.DataFrame) -> str | None:
    direct = choose_by_alias(df, [
        "product_name", "canonical_product_name", "canonical_name", "sealed_product_name",
        "display_name", "product", "name", "title", "set_name",
    ])
    if direct:
        return direct
    best_col = None
    best_count = 0
    for col in df.columns:
        series = df[col].astype(str)
        count = int(series.str.contains("collector booster", case=False, na=False).sum())
        if count > best_count:
            best_col = str(col)
            best_count = count
    return best_col if best_count > 0 else None


def value(row: pd.Series, aliases: list[str], default: object = "") -> object:
    lower = {str(c).lower(): c for c in row.index}
    for alias in aliases:
        col = lower.get(alias.lower())
        if col is None:
            continue
        v = row[col]
        if pd.notna(v) and str(v).strip() not in {"", "nan", "None"}:
            return v
    return default


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []

    for path in SOURCES:
        df = read_csv(path)
        name_col = choose_name_column(df) if not df.empty else None
        diagnostics.append({
            "source_path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "detected_name_column": name_col or "UNMAPPED",
            "columns": "|".join(map(str, df.columns)),
        })
        if df.empty or name_col is None:
            continue
        mask = df[name_col].astype(str).str.contains("collector booster", case=False, na=False)
        for _, row in df.loc[mask].iterrows():
            name = str(row[name_col]).strip()
            rows.append({
                "product_key": str(value(row, ["product_key", "tcgplayer_product_id", "product_id", "canonical_product_id"], norm(name))),
                "product_name": name,
                "release_date": value(row, ["release_date", "set_release_date", "first_release_date", "launch_date"], "NOT_AVAILABLE"),
                "market_price": value(row, ["market_price", "current_market_price", "price", "market_value", "tcg_market_price"], "NOT_AVAILABLE"),
                "listing_count": value(row, ["listing_count", "active_listing_count"], "NOT_AVAILABLE"),
                "sales_count": value(row, ["sales_count", "sold_count"], "NOT_AVAILABLE"),
                "demand_score": value(row, ["demand_score", "demand_durability_score"], "NOT_AVAILABLE"),
                "franchise_strength": value(row, ["franchise_strength", "franchise_score"], "NOT_AVAILABLE"),
                "source_lineage": str(path.relative_to(ROOT)),
                "normalized_name": norm(name),
            })

    universe = pd.DataFrame(rows)
    if not universe.empty:
        priority = {str(SOURCES[0].relative_to(ROOT)): 0, str(SOURCES[1].relative_to(ROOT)): 1}
        universe["source_priority"] = universe["source_lineage"].map(priority).fillna(99)
        universe = universe.sort_values(["normalized_name", "source_priority"]).drop_duplicates("normalized_name", keep="first")
        universe = universe.drop(columns=["source_priority"]).sort_values("product_name")
    else:
        universe = pd.DataFrame(columns=[
            "product_key", "product_name", "release_date", "market_price", "listing_count",
            "sales_count", "demand_score", "franchise_strength", "source_lineage", "normalized_name",
        ])

    universe.to_csv(OUT / "collector_early_lifecycle_canonical_universe.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(OUT / "collector_early_lifecycle_universe_source_diagnostics.csv", index=False)

    result = {
        "audit_name": "Collector Early-Lifecycle Universe Adapter",
        "audit_version": "1.0.0",
        "source_count": len(SOURCES),
        "mapped_source_count": int(sum(1 for x in diagnostics if x["detected_name_column"] != "UNMAPPED")),
        "canonical_product_count": int(len(universe)),
        "status": "PASS" if len(universe) > 0 else "FAIL",
    }
    (OUT / "collector_early_lifecycle_universe_adapter_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if len(universe) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
