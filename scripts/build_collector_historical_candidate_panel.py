"""Build a governed, source-preserving Collector historical candidate panel.

Only exact TCGplayer product-ID rows from configured primary sources may be
selected automatically. Name-only sources are inventoried separately and never
auto-selected. This script creates candidate governance outputs only; it does
not modify source ledgers or authorize history, forecasting, or purchases.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_historical_source_precedence_v1.json"
DEFAULT_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_current_authority/collector_current_authority_all.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_historical_candidate_panel"

ID_CANDIDATES = ["tcgplayer_product_id", "product_id", "productId"]
DATE_CANDIDATES = ["observation_date", "date", "price_date", "month", "timestamp", "collected_at", "source_timestamp"]
PRICE_CANDIDATES = ["market_price", "price", "close", "value"]
NAME_CANDIDATES = ["box_name", "product_name", "name", "canonical_product_name", "set_name"]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build Collector historical candidate panel")
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_id(value: object) -> str:
    value = text(value)
    return value[:-2] if value.endswith(".0") else value


def first_col(frame: pd.DataFrame, candidates: list[str]) -> str:
    lookup = {str(c).lower(): str(c) for c in frame.columns}
    return next((lookup[c.lower()] for c in candidates if c.lower() in lookup), "")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")


def main() -> int:
    args = parser().parse_args()
    policy_path = args.policy.resolve()
    authority_path = args.authority.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    if not policy_path.is_file():
        failures.append("source_precedence_policy_missing")
    if not authority_path.is_file():
        failures.append("collector_current_authority_missing")
    if failures:
        summary = {"status": "FAIL", "failures": failures, "historical_append_authorized": False, "forecasting_resume_authorized": False, "purchase_recommendation_authorized": False}
        (out / "collector_historical_candidate_panel_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    policy = json.loads(policy_path.read_text(encoding="utf-8-sig"))
    authority = read_csv(authority_path)
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)
    governed = authority.loc[authority["identity_authority_status"].eq("CURRENT_IDENTITY_AUTHORIZED")].copy()
    governed_ids = set(governed["tcgplayer_product_id"])
    governed_release = governed.set_index("tcgplayer_product_id")["release_state"].to_dict()
    governed_name = governed.set_index("tcgplayer_product_id")["box_name"].to_dict()

    normalized_frames: list[pd.DataFrame] = []
    source_audit: list[dict[str, object]] = []
    source_errors: list[dict[str, str]] = []

    for source in policy["primary_exact_id_sources"]:
        rel = source["path"]
        path = ROOT / rel
        precedence = int(source["precedence"])
        if not path.is_file():
            source_errors.append({"path": rel, "error_type": "FileNotFoundError", "error_message": "configured source missing"})
            continue
        try:
            frame = read_csv(path)
            id_col = first_col(frame, ID_CANDIDATES)
            date_col = first_col(frame, DATE_CANDIDATES)
            price_col = first_col(frame, PRICE_CANDIDATES)
            name_col = first_col(frame, NAME_CANDIDATES)
            if not id_col or not date_col or not price_col:
                source_errors.append({"path": rel, "error_type": "SchemaError", "error_message": f"required columns missing id={id_col!r} date={date_col!r} price={price_col!r}"})
                continue
            n = pd.DataFrame({
                "tcgplayer_product_id": frame[id_col].map(norm_id),
                "source_observation_date": frame[date_col].map(text),
                "source_market_price": pd.to_numeric(frame[price_col], errors="coerce"),
                "source_product_name": frame[name_col].map(text) if name_col else "",
            })
            n["source_path"] = rel
            n["source_precedence"] = precedence
            n["source_row_number"] = range(2, len(n) + 2)
            n["governed_product"] = n["tcgplayer_product_id"].isin(governed_ids)
            n["parsed_date"] = pd.to_datetime(n["source_observation_date"], errors="coerce", utc=True)
            n["observation_month"] = n["parsed_date"].dt.strftime("%Y-%m-01")
            n["positive_price"] = n["source_market_price"].gt(0)
            n["release_state"] = n["tcgplayer_product_id"].map(governed_release).fillna("")
            n["governed_box_name"] = n["tcgplayer_product_id"].map(governed_name).fillna("")
            normalized_frames.append(n)
            source_audit.append({
                "path": rel,
                "precedence": precedence,
                "source_rows": int(len(frame)),
                "governed_rows": int(n["governed_product"].sum()),
                "valid_date_rows": int(n["parsed_date"].notna().sum()),
                "positive_price_rows": int(n["positive_price"].sum()),
                "eligible_candidate_rows": int((n["governed_product"] & n["parsed_date"].notna() & n["positive_price"]).sum()),
                "identity_column": id_col,
                "date_column": date_col,
                "price_column": price_col,
            })
        except Exception as exc:
            source_errors.append({"path": rel, "error_type": type(exc).__name__, "error_message": str(exc)[:500]})

    if normalized_frames:
        all_rows = pd.concat(normalized_frames, ignore_index=True)
    else:
        all_rows = pd.DataFrame(columns=["tcgplayer_product_id", "source_observation_date", "source_market_price", "source_product_name", "source_path", "source_precedence", "source_row_number", "governed_product", "parsed_date", "observation_month", "positive_price", "release_state", "governed_box_name"])

    eligible = all_rows.loc[
        all_rows["governed_product"]
        & all_rows["parsed_date"].notna()
        & all_rows["positive_price"]
    ].copy()
    eligible["product_month_key"] = eligible["tcgplayer_product_id"] + "|" + eligible["observation_month"]

    same_source_duplicates = eligible.loc[
        eligible.duplicated(["source_path", "tcgplayer_product_id", "observation_month"], keep=False)
    ].sort_values(["source_path", "tcgplayer_product_id", "observation_month", "source_row_number"])

    eligible = eligible.sort_values(["tcgplayer_product_id", "observation_month", "source_precedence", "source_path", "source_row_number"])
    selected = eligible.drop_duplicates(["tcgplayer_product_id", "observation_month"], keep="first").copy()
    selected["selection_status"] = "CANDIDATE_SELECTED_BY_PRECEDENCE"
    selected["historical_append_authorized"] = False

    counts = eligible.groupby(["tcgplayer_product_id", "observation_month"]).agg(
        candidate_row_count=("source_path", "size"),
        distinct_source_count=("source_path", "nunique"),
        distinct_price_count=("source_market_price", "nunique"),
        minimum_price=("source_market_price", "min"),
        maximum_price=("source_market_price", "max"),
    ).reset_index()
    conflicts = counts.loc[(counts["candidate_row_count"] > 1) & (counts["distinct_price_count"] > 1)].copy()
    conflicts["absolute_price_spread"] = conflicts["maximum_price"] - conflicts["minimum_price"]
    conflicts["relative_price_spread"] = conflicts["absolute_price_spread"] / conflicts["minimum_price"].replace(0, pd.NA)

    product_coverage = selected.groupby("tcgplayer_product_id").agg(
        selected_months=("observation_month", "nunique"),
        first_month=("observation_month", "min"),
        last_month=("observation_month", "max"),
        selected_source_count=("source_path", "nunique"),
    ).reset_index()
    product_coverage["governed_box_name"] = product_coverage["tcgplayer_product_id"].map(governed_name).fillna("")
    product_coverage["release_state"] = product_coverage["tcgplayer_product_id"].map(governed_release).fillna("")
    missing_products = governed.loc[~governed["tcgplayer_product_id"].isin(set(product_coverage["tcgplayer_product_id"]))].copy()

    all_rows.to_csv(out / "collector_historical_source_specific_rows.csv", index=False)
    eligible.to_csv(out / "collector_historical_exact_id_candidates.csv", index=False)
    selected.to_csv(out / "collector_historical_candidate_panel.csv", index=False)
    same_source_duplicates.to_csv(out / "collector_historical_same_source_duplicates.csv", index=False)
    conflicts.to_csv(out / "collector_historical_cross_source_conflicts.csv", index=False)
    product_coverage.to_csv(out / "collector_historical_product_coverage.csv", index=False)
    missing_products.to_csv(out / "collector_historical_governed_products_without_history.csv", index=False)
    pd.DataFrame(source_audit).to_csv(out / "collector_historical_source_selection_audit.csv", index=False)
    pd.DataFrame(source_errors, columns=["path", "error_type", "error_message"]).to_csv(out / "collector_historical_source_selection_errors.csv", index=False)

    summary = {
        "block_name": "Collector Historical Candidate Panel",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governed_product_rows": int(len(governed)),
        "configured_primary_sources": int(len(policy["primary_exact_id_sources"])),
        "sources_loaded": int(len(source_audit)),
        "source_errors": int(len(source_errors)),
        "source_specific_rows": int(len(all_rows)),
        "eligible_exact_id_rows": int(len(eligible)),
        "selected_product_month_rows": int(len(selected)),
        "selected_products": int(selected["tcgplayer_product_id"].nunique()) if len(selected) else 0,
        "same_source_duplicate_rows": int(len(same_source_duplicates)),
        "cross_source_conflict_keys": int(len(conflicts)),
        "governed_products_without_history": int(len(missing_products)),
        "presale_selected_rows": int(selected["release_state"].eq("PRESALE").sum()) if len(selected) else 0,
        "fixed_product_count_assumed": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_CANDIDATE_PANEL_ONLY" if len(selected) and not source_errors else "REVIEW_REQUIRED",
        "failures": [],
    }
    (out / "collector_historical_candidate_panel_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if args.strict and (source_errors or not len(selected)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
