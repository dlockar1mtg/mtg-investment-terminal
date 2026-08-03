from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/mtg/governance/collector_v1_authoritative_data_registry.json"
BASE = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_foundation"
MATRIX_PATH = BASE / "collector_v1_authoritative_feature_matrix.csv"
LINEAGE_PATH = BASE / "collector_v1_source_to_feature_lineage.csv"
COVERAGE_PATH = BASE / "collector_v1_authoritative_feature_coverage.csv"
SUMMARY_PATH = BASE / "collector_v1_authoritative_feature_foundation_summary.json"


def normalize_product_id(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    extracted = text.str.extract(r"(\d+)$", expand=False)
    return extracted.fillna(text)


def first_column(df: pd.DataFrame, names: list[str]) -> str | None:
    lookup = {str(c).strip().lower(): str(c) for c in df.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def parse_pack_count(value) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).lower()
    patterns = [
        r"(\d+)\s*[- ]?pack",
        r"(\d+)\s*booster",
        r"display\s*of\s*(\d+)",
        r"contains\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return np.nan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if not MATRIX_PATH.exists() or not SUMMARY_PATH.exists():
        raise FileNotFoundError("Authoritative feature build artifacts do not exist; run the build first.")

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matrix = pd.read_csv(MATRIX_PATH, low_memory=False)
    lineage = pd.read_csv(LINEAGE_PATH, low_memory=False)
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    active_ids = set(normalize_product_id(matrix["tcgplayer_product_id"]).dropna())

    comparable_path = ROOT / registry["authorities"]["comparables"]["path"]
    comparables = pd.read_csv(comparable_path, low_memory=False)
    target_col = first_column(comparables, ["target_tcgplayer_product_id", "target_product_id", "target_investment_product_id", "investment_product_id"])
    peer_col = first_column(comparables, ["peer_tcgplayer_product_id", "peer_product_id", "comparable_product_id", "selected_peer_product_id"])
    score_col = first_column(comparables, ["similarity_score", "comparable_score", "pair_score", "score", "selection_score"])
    weight_col = first_column(comparables, ["peer_weight", "weight", "normalized_weight", "selection_weight"])
    if not target_col:
        raise ValueError(f"Comparable target identity column unresolved; available={list(comparables.columns)}")

    c = comparables.copy()
    c["tcgplayer_product_id"] = normalize_product_id(c[target_col])
    c = c[c["tcgplayer_product_id"].isin(active_ids)]
    c["peer_id"] = normalize_product_id(c[peer_col]) if peer_col else pd.NA
    c["score_value"] = pd.to_numeric(c[score_col], errors="coerce") if score_col else np.nan
    c["weight_value"] = pd.to_numeric(c[weight_col], errors="coerce") if weight_col else np.nan
    comp_features = c.groupby("tcgplayer_product_id", as_index=False).agg(
        selected_comparable_rows=("tcgplayer_product_id", "size"),
        selected_comparable_unique_peers=("peer_id", lambda s: int(s.dropna().nunique())),
        comparable_mean_score=("score_value", "mean"),
        comparable_weight_sum=("weight_value", "sum"),
    )

    for col in ["selected_comparable_rows", "selected_comparable_unique_peers", "comparable_mean_score", "comparable_weight_sum"]:
        if col in matrix.columns:
            matrix = matrix.drop(columns=[col])
    matrix = matrix.merge(comp_features, on="tcgplayer_product_id", how="left")
    matrix["selected_comparable_rows"] = pd.to_numeric(matrix["selected_comparable_rows"], errors="coerce").fillna(0).astype(int)
    matrix["selected_comparable_unique_peers"] = pd.to_numeric(matrix["selected_comparable_unique_peers"], errors="coerce").fillna(0).astype(int)

    structure_path = ROOT / registry["authorities"]["structural_authority"]["path"]
    structure = pd.read_csv(structure_path, low_memory=False)
    id_col = first_column(structure, ["tcgplayer_product_id", "product_id", "tcgplayer_id", "investment_product_id"])
    if not id_col:
        raise ValueError(f"Structural identity column unresolved; available={list(structure.columns)}")
    structure["tcgplayer_product_id"] = normalize_product_id(structure[id_col])
    structure = structure[structure["tcgplayer_product_id"].isin(active_ids)]

    config_col = first_column(structure, ["product_configuration", "configuration", "sealed_configuration", "display_configuration"])
    family_col = first_column(structure, ["product_family", "set_name", "governed_box_name", "source_product_name", "product_name"])
    topper_col = first_column(structure, ["box_topper", "has_box_topper", "box_topper_status", "topper_included"])
    licensed_col = first_column(structure, ["licensed_ip", "is_licensed_ip", "universes_beyond", "licensed_property"])
    edition_col = first_column(structure, ["edition_classification", "edition_type", "product_edition", "classification"])

    s = structure[["tcgplayer_product_id"]].copy()
    s["product_configuration"] = structure[config_col] if config_col else pd.NA
    s["pack_count"] = structure[config_col].map(parse_pack_count) if config_col else np.nan
    s["product_family"] = structure[family_col] if family_col else pd.NA
    s["box_topper"] = structure[topper_col] if topper_col else pd.NA
    s["licensed_ip"] = structure[licensed_col] if licensed_col else pd.NA
    s["edition_classification"] = structure[edition_col] if edition_col else "COLLECTOR_BOOSTER_DISPLAY"
    s = s.groupby("tcgplayer_product_id", as_index=False).first()

    for col in ["product_configuration", "pack_count", "product_family", "box_topper", "licensed_ip", "edition_classification"]:
        if col in matrix.columns:
            matrix = matrix.drop(columns=[col])
    matrix = matrix.merge(s, on="tcgplayer_product_id", how="left")

    matrix["comparable_eligible_v1"] = matrix["selected_comparable_rows"].gt(0)
    matrix["forecast_experiment_eligible_v1"] = matrix["direct_history_eligible_v1"].astype(bool) | matrix["comparable_eligible_v1"]

    optional_unavailable = []
    if not topper_col:
        optional_unavailable.append("box_topper")
    if not licensed_col:
        optional_unavailable.append("licensed_ip")
    if matrix["pack_count"].notna().sum() == 0:
        optional_unavailable.append("pack_count")

    lineage = lineage[~lineage["feature"].isin([
        "selected_comparable_rows", "pack_count", "box_topper", "licensed_ip", "product_family", "edition_classification", "product_configuration"
    ])].copy()
    additions = [
        {"feature": "selected_comparable_rows", "authority_key": "comparables", "authority_path": registry["authorities"]["comparables"]["path"], "source_column": target_col, "transformation": "NORMALIZE_TRAILING_PRODUCT_ID_AND_COUNT_ROWS", "join_key": "tcgplayer_product_id"},
        {"feature": "product_configuration", "authority_key": "structural_authority", "authority_path": registry["authorities"]["structural_authority"]["path"], "source_column": config_col or "NOT_AVAILABLE", "transformation": "DIRECT_JOIN" if config_col else "OPTIONAL_NOT_AVAILABLE", "join_key": "tcgplayer_product_id"},
        {"feature": "pack_count", "authority_key": "structural_authority", "authority_path": registry["authorities"]["structural_authority"]["path"], "source_column": config_col or "NOT_AVAILABLE", "transformation": "REGEX_PARSE_EXPLICIT_PACK_COUNT" if config_col else "OPTIONAL_NOT_AVAILABLE", "join_key": "tcgplayer_product_id"},
        {"feature": "product_family", "authority_key": "structural_authority", "authority_path": registry["authorities"]["structural_authority"]["path"], "source_column": family_col or "NOT_AVAILABLE", "transformation": "DIRECT_JOIN" if family_col else "OPTIONAL_NOT_AVAILABLE", "join_key": "tcgplayer_product_id"},
        {"feature": "box_topper", "authority_key": "structural_authority", "authority_path": registry["authorities"]["structural_authority"]["path"], "source_column": topper_col or "NOT_AVAILABLE_OPTIONAL_V1", "transformation": "DIRECT_JOIN" if topper_col else "OPTIONAL_NOT_AVAILABLE", "join_key": "tcgplayer_product_id"},
        {"feature": "licensed_ip", "authority_key": "structural_authority", "authority_path": registry["authorities"]["structural_authority"]["path"], "source_column": licensed_col or "NOT_AVAILABLE_OPTIONAL_V1", "transformation": "DIRECT_JOIN" if licensed_col else "OPTIONAL_NOT_AVAILABLE", "join_key": "tcgplayer_product_id"},
        {"feature": "edition_classification", "authority_key": "active_universe", "authority_path": registry["authorities"]["active_universe"]["path"], "source_column": edition_col or "ACTIVE_UNIVERSE_POLICY", "transformation": "DIRECT_JOIN" if edition_col else "CONSTANT_FROM_COLLECTOR_DISPLAY_UNIVERSE_POLICY", "join_key": "tcgplayer_product_id"},
    ]
    lineage = pd.concat([lineage, pd.DataFrame(additions)], ignore_index=True)

    key_features = [
        "current_price_authoritative", "release_date_authoritative", "supply_scarcity_index_v1", "history_months",
        "return_90d", "return_180d", "return_365d", "annualized_volatility", "maximum_drawdown",
        "selected_comparable_rows", "pack_count", "box_topper", "licensed_ip", "product_family", "edition_classification"
    ]
    coverage_rows = []
    for feature in key_features:
        if feature == "selected_comparable_rows":
            nonmissing = int(matrix[feature].gt(0).sum())
        else:
            nonmissing = int(matrix[feature].notna().sum()) if feature in matrix.columns else 0
        coverage_rows.append({"feature": feature, "nonmissing_rows": nonmissing, "total_rows": len(matrix), "coverage_rate": nonmissing / len(matrix) if len(matrix) else 0})
    coverage = pd.DataFrame(coverage_rows)

    blockers = []
    if len(matrix) != 50 or matrix["tcgplayer_product_id"].astype(str).nunique() != 50:
        blockers.append("Active universe is not exactly 50 unique products.")
    if matrix["current_price_authoritative"].isna().any():
        blockers.append("One or more active products lack authoritative current price.")
    if int(summary.get("history_diagnostics", {}).get("covered_active_products", 0)) == 0:
        blockers.append("Safe monthly history did not join to any active product.")
    if comp_features["tcgplayer_product_id"].nunique() == 0:
        blockers.append("Comparable authority did not join to any active product.")
    if int(matrix["forecast_experiment_eligible_v1"].sum()) == 0:
        blockers.append("No active product is forecast-experiment eligible after authoritative joins.")

    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    summary["comparable_diagnostics"] = {
        "target_column": target_col,
        "peer_column": peer_col,
        "score_column": score_col,
        "weight_column": weight_col,
        "matched_rows": int(len(c)),
        "covered_active_products": int(comp_features["tcgplayer_product_id"].nunique()),
        "identity_normalization": "TRAILING_NUMERIC_PRODUCT_ID_FROM_VALUE",
    }
    summary["structural_diagnostics"] = {
        "id_column": id_col,
        "chosen_columns": {
            "product_configuration": config_col,
            "pack_count": config_col,
            "product_family": family_col,
            "box_topper": topper_col,
            "licensed_ip": licensed_col,
            "edition_classification": edition_col or "ACTIVE_UNIVERSE_POLICY",
        },
        "covered_active_products": int(s["tcgplayer_product_id"].nunique()),
        "optional_unavailable_features": optional_unavailable,
    }
    summary["direct_history_eligible_rows"] = int(matrix["direct_history_eligible_v1"].sum())
    summary["comparable_eligible_rows"] = int(matrix["comparable_eligible_v1"].sum())
    summary["forecast_experiment_eligible_rows"] = int(matrix["forecast_experiment_eligible_v1"].sum())
    summary["blockers"] = blockers
    summary["authoritative_feature_foundation_ready"] = not blockers
    summary["forecast_experiments_authorized"] = not blockers
    summary["production_forecasting_authorized"] = False
    summary["purchase_recommendations_authorized"] = False
    summary["uip_delivery_authorized"] = False
    summary["status"] = "PASS_COLLECTOR_V1_AUTHORITATIVE_FEATURE_FOUNDATION_READY" if not blockers else "BLOCKED_COLLECTOR_V1_AUTHORITATIVE_FEATURE_FOUNDATION"

    matrix.to_csv(MATRIX_PATH, index=False)
    lineage.to_csv(LINEAGE_PATH, index=False)
    coverage.to_csv(COVERAGE_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
