from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/operations/collector_long_horizon_historical_feature_panel/candidate_v1_0_0/collector_long_horizon_monthly_price_panel.csv"
OUT = ROOT / "data/operations/collector_early_lifecycle_monthly_replay/candidate_v1_0_0"

PRICE_TOKENS = ("price", "value", "market", "tcg", "low", "mid", "high")
DATE_TOKENS = ("date", "month", "time", "observed", "as_of")


def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    try:
        df = pd.read_csv(SOURCE, low_memory=False)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        df = pd.DataFrame()

    if df.empty:
        failures.append("monthly_price_panel_missing_or_empty")

    coverage_rows: list[dict[str, object]] = []
    if not df.empty:
        for column in df.columns:
            name = str(column)
            lower = name.lower()
            numeric = safe_numeric(df[column])
            positive = numeric > 0
            nonblank = df[column].astype(str).str.strip().ne("") & df[column].notna()
            coverage_rows.append({
                "column_name": name,
                "looks_like_price": any(token in lower for token in PRICE_TOKENS),
                "looks_like_date": any(token in lower for token in DATE_TOKENS),
                "nonblank_count": int(nonblank.sum()),
                "numeric_count": int(numeric.notna().sum()),
                "positive_numeric_count": int(positive.sum()),
                "positive_numeric_pct": float(positive.mean()),
                "minimum_positive": float(numeric[positive].min()) if positive.any() else None,
                "median_positive": float(numeric[positive].median()) if positive.any() else None,
                "maximum_positive": float(numeric[positive].max()) if positive.any() else None,
            })

    coverage = pd.DataFrame(coverage_rows)
    coverage_path = OUT / "collector_monthly_price_panel_column_coverage.csv"
    coverage.to_csv(coverage_path, index=False)

    price_candidates = coverage[coverage["looks_like_price"] == True].copy() if not coverage.empty else pd.DataFrame()
    price_candidates = price_candidates.sort_values(
        ["positive_numeric_count", "numeric_count", "nonblank_count"],
        ascending=False,
    ) if not price_candidates.empty else price_candidates

    selected_price_column = str(price_candidates.iloc[0]["column_name"]) if not price_candidates.empty else "UNMAPPED"
    selected_positive_count = int(price_candidates.iloc[0]["positive_numeric_count"]) if not price_candidates.empty else 0

    if selected_positive_count == 0:
        failures.append("no_positive_numeric_price_column")

    result = {
        "audit_name": "Collector Monthly Price Panel Coverage Audit",
        "audit_version": "1.0.0",
        "source_row_count": int(len(df)),
        "source_column_count": int(len(df.columns)) if not df.empty else 0,
        "price_candidate_count": int(len(price_candidates)),
        "selected_price_column_by_coverage": selected_price_column,
        "selected_positive_numeric_count": selected_positive_count,
        "current_market_price_positive_count": int((safe_numeric(df["market_price"]) > 0).sum()) if "market_price" in df.columns else 0,
        "coverage_output": str(coverage_path.relative_to(ROOT)),
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }

    summary_path = OUT / "collector_monthly_price_panel_coverage_summary.json"
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
