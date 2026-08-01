from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_early_lifecycle_universe/candidate_v1_0_0"
PRODUCT_MASTER = ROOT / "data/product_master/product_master_model_input.csv"
GOVERNED_REGISTRY = ROOT / "data/validation/phase_10/collector_booster_boxes/governed_registry/collector_booster_box_governed_registry.csv"
SOURCES = [PRODUCT_MASTER, GOVERNED_REGISTRY]
NA = "NOT_AVAILABLE"


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
    """Choose the column that actually contains Collector product names."""
    best_col: str | None = None
    best_count = 0
    for col in df.columns:
        series = df[col].astype(str)
        count = int(series.str.contains("collector booster", case=False, na=False).sum())
        if count > best_count:
            best_col = str(col)
            best_count = count
    if best_count > 0:
        return best_col
    return choose_by_alias(df, [
        "canonical_product_name", "approved_product_name", "official_product_name",
        "box_name", "box_name_master", "product_name", "sealed_product_name",
        "display_name", "product", "name", "title", "set_name",
    ])


def value(row: pd.Series, aliases: list[str], default: object = "") -> object:
    lower = {str(c).lower(): c for c in row.index}
    for alias in aliases:
        col = lower.get(alias.lower())
        if col is None:
            continue
        v = row[col]
        if pd.notna(v) and str(v).strip() not in {"", "nan", "None", NA}:
            return v
    return default


def clean_id(value_in: object) -> str:
    text = str(value_in or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def first_available(group: pd.DataFrame, column: str, preferred_source: str | None = None) -> object:
    ordered = group.copy()
    if preferred_source is not None:
        ordered["_preferred"] = ordered["source_lineage"].eq(preferred_source).astype(int)
        ordered = ordered.sort_values("_preferred", ascending=False)
    for item in ordered[column].tolist():
        if pd.notna(item) and str(item).strip() not in {"", "nan", "None", NA}:
            return item
    return NA


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []

    registry_source = str(GOVERNED_REGISTRY.relative_to(ROOT))
    master_source = str(PRODUCT_MASTER.relative_to(ROOT))

    for path in SOURCES:
        df = read_csv(path)
        name_col = choose_name_column(df) if not df.empty else None
        collector_count = 0
        if not df.empty and name_col is not None:
            collector_count = int(df[name_col].astype(str).str.contains("collector booster", case=False, na=False).sum())
        diagnostics.append({
            "source_path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "detected_name_column": name_col or "UNMAPPED",
            "collector_name_row_count": collector_count,
            "columns": "|".join(map(str, df.columns)),
        })
        if df.empty or name_col is None:
            continue

        mask = df[name_col].astype(str).str.contains("collector booster", case=False, na=False)
        for _, row in df.loc[mask].iterrows():
            name = str(row[name_col]).strip()
            tcgplayer_id = clean_id(value(row, [
                "tcgplayer_product_id", "approved_tcgplayer_product_id",
                "approved_tcgplayer_product_id_str", "tcgplayer_product_id_str",
            ], ""))
            canonical_id = clean_id(value(row, [
                "canonical_product_id", "investment_product_id", "product_id",
            ], ""))
            product_key = tcgplayer_id or canonical_id or norm(name)
            rows.append({
                "product_key": product_key,
                "tcgplayer_product_id": tcgplayer_id or NA,
                "canonical_product_id": canonical_id or NA,
                "product_name": name,
                "release_date": value(row, [
                    "release_date", "set_release_date", "first_release_date",
                    "launch_date", "published_on",
                ], NA),
                "market_price": value(row, [
                    "market_price", "current_market_price", "current_price",
                    "current_price_history", "current_price_db", "price",
                    "market_value", "tcg_market_price",
                ], NA),
                "listing_count": value(row, [
                    "listing_count", "active_listing_count", "inventory_count",
                ], NA),
                "sales_count": value(row, [
                    "sales_count", "sold_count", "observations",
                ], NA),
                "supply_score": value(row, [
                    "supply_score", "inventory_signal_score", "scarcity_signal_score",
                ], NA),
                "demand_score": value(row, [
                    "demand_score", "real_demand_score", "demand_durability_score",
                ], NA),
                "franchise_strength": value(row, [
                    "franchise_strength", "franchise_score", "ip_score",
                ], NA),
                "liquidity_score": value(row, [
                    "liquidity_score", "liquidity_proxy_score", "real_signal_score",
                ], NA),
                "reprint_risk": value(row, ["reprint_risk"], NA),
                "source_lineage": str(path.relative_to(ROOT)),
                "normalized_name": norm(name),
            })

    raw = pd.DataFrame(rows)
    output_columns = [
        "product_key", "tcgplayer_product_id", "canonical_product_id", "product_name",
        "release_date", "market_price", "listing_count", "sales_count", "supply_score",
        "demand_score", "franchise_strength", "liquidity_score", "reprint_risk",
        "source_lineage", "normalized_name",
    ]

    merged_rows: list[dict[str, object]] = []
    if not raw.empty:
        registry = raw[raw["source_lineage"] == registry_source].copy()
        master = raw[raw["source_lineage"] == master_source].copy()

        id_to_registry_name = {
            clean_id(r["tcgplayer_product_id"]): str(r["normalized_name"])
            for _, r in registry.iterrows()
            if clean_id(r["tcgplayer_product_id"]) not in {"", NA}
        }
        master["merge_identity"] = master.apply(
            lambda r: id_to_registry_name.get(
                clean_id(r["tcgplayer_product_id"]), str(r["normalized_name"])
            ),
            axis=1,
        )
        registry["merge_identity"] = registry["normalized_name"]
        combined = pd.concat([registry, master], ignore_index=True)

        for identity, group in combined.groupby("merge_identity", dropna=False):
            canonical_name = first_available(group, "product_name", registry_source)
            tcgplayer_id = clean_id(first_available(group, "tcgplayer_product_id", registry_source))
            if tcgplayer_id in {"", NA}:
                tcgplayer_id = clean_id(first_available(group, "tcgplayer_product_id", master_source))
            canonical_id = clean_id(first_available(group, "canonical_product_id", registry_source))
            if canonical_id in {"", NA}:
                canonical_id = clean_id(first_available(group, "canonical_product_id", master_source))
            canonical_key = tcgplayer_id or canonical_id or norm(canonical_name)
            lineage = "|".join(sorted(set(group["source_lineage"].astype(str))))
            merged_rows.append({
                "product_key": canonical_key,
                "tcgplayer_product_id": tcgplayer_id or NA,
                "canonical_product_id": canonical_id or NA,
                "product_name": canonical_name,
                "release_date": first_available(group, "release_date", registry_source),
                "market_price": first_available(group, "market_price", master_source),
                "listing_count": first_available(group, "listing_count", master_source),
                "sales_count": first_available(group, "sales_count", master_source),
                "supply_score": first_available(group, "supply_score", master_source),
                "demand_score": first_available(group, "demand_score", master_source),
                "franchise_strength": first_available(group, "franchise_strength", master_source),
                "liquidity_score": first_available(group, "liquidity_score", master_source),
                "reprint_risk": first_available(group, "reprint_risk", master_source),
                "source_lineage": lineage,
                "normalized_name": norm(canonical_name),
            })

    universe = pd.DataFrame(merged_rows, columns=output_columns)
    if not universe.empty:
        universe["product_key"] = universe["product_key"].map(clean_id)
        universe["tcgplayer_product_id"] = universe["tcgplayer_product_id"].map(clean_id)
        universe["canonical_product_id"] = universe["canonical_product_id"].map(clean_id)
        universe = universe.drop_duplicates("product_key", keep="first").sort_values("product_name")
    else:
        universe = pd.DataFrame(columns=output_columns)

    universe.to_csv(OUT / "collector_early_lifecycle_canonical_universe.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(OUT / "collector_early_lifecycle_universe_source_diagnostics.csv", index=False)

    result = {
        "audit_name": "Collector Early-Lifecycle Universe Adapter",
        "audit_version": "1.2.0",
        "identity_contract": "TCGPLAYER_PRODUCT_ID_PRIMARY",
        "source_count": len(SOURCES),
        "mapped_source_count": int(sum(1 for x in diagnostics if x["detected_name_column"] != "UNMAPPED")),
        "canonical_product_count": int(len(universe)),
        "release_date_coverage_count": int((universe["release_date"].astype(str) != NA).sum()) if not universe.empty else 0,
        "market_price_coverage_count": int((universe["market_price"].astype(str) != NA).sum()) if not universe.empty else 0,
        "tcgplayer_identity_coverage_count": int((universe["tcgplayer_product_id"].astype(str) != NA).sum()) if not universe.empty else 0,
        "multi_source_lineage_count": int(universe["source_lineage"].astype(str).str.contains("\\|").sum()) if not universe.empty else 0,
        "status": "PASS" if len(universe) > 0 else "FAIL",
    }
    (OUT / "collector_early_lifecycle_universe_adapter_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if len(universe) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
