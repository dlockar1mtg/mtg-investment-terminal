"""Build a safe Collector monthly history candidate from proven monthly-grain sources only."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAIN_AUDIT = ROOT / "data/governance/permanence/certification/collector_historical_source_grain/collector_historical_source_grain_audit.csv"
DEFAULT_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_current_authority/collector_current_authority_all.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_safe_monthly_history"

ID_COLS = ["tcgplayer_product_id", "product_id", "productId"]
DATE_COLS = ["observation_date", "date", "price_date", "month", "timestamp", "collected_at", "source_timestamp"]
PRICE_COLS = ["market_price", "monthly_market_price", "selected_market_price", "close", "price"]
NAME_COLS = ["box_name", "product_name", "name", "canonical_product_name", "set_name"]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build safe Collector monthly history candidate")
    p.add_argument("--grain-audit", type=Path, default=DEFAULT_GRAIN_AUDIT)
    p.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")


def first_col(frame: pd.DataFrame, candidates: list[str]) -> str:
    lookup = {str(c).lower(): str(c) for c in frame.columns}
    return next((lookup[x.lower()] for x in candidates if x.lower() in lookup), "")


def norm_id(value: object) -> str:
    value = "" if pd.isna(value) else str(value).strip()
    return value[:-2] if value.endswith(".0") else value


def main() -> int:
    args = parser().parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    authority = read_csv(args.authority.resolve())
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)
    governed = authority.loc[authority["identity_authority_status"].eq("CURRENT_IDENTITY_AUTHORIZED")].copy()
    governed_ids = set(governed["tcgplayer_product_id"])
    name_map = governed.set_index("tcgplayer_product_id")["box_name"].to_dict()
    release_map = governed.set_index("tcgplayer_product_id")["release_state"].to_dict()

    audit = read_csv(args.grain_audit.resolve())
    safe_paths = audit.loc[audit["safe_for_monthly_market_selection"].str.lower().eq("true"), "path"].tolist()

    rows: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []
    for precedence, rel in enumerate(safe_paths, start=1):
        path = ROOT / rel
        try:
            frame = read_csv(path)
            id_col = first_col(frame, ID_COLS)
            date_col = first_col(frame, DATE_COLS)
            price_col = first_col(frame, PRICE_COLS)
            name_col = first_col(frame, NAME_COLS)
            if not id_col or not date_col or not price_col:
                raise ValueError(f"required columns missing id={id_col!r} date={date_col!r} price={price_col!r}")
            n = pd.DataFrame({
                "tcgplayer_product_id": frame[id_col].map(norm_id),
                "source_observation_date": frame[date_col].astype(str),
                "source_market_price": pd.to_numeric(frame[price_col], errors="coerce"),
                "source_product_name": frame[name_col].astype(str) if name_col else "",
            })
            n["parsed_date"] = pd.to_datetime(n["source_observation_date"], errors="coerce", utc=True)
            n["observation_month"] = n["parsed_date"].dt.strftime("%Y-%m-01")
            n["source_path"] = rel
            n["source_precedence"] = precedence
            n["source_row_number"] = range(2, len(n) + 2)
            n = n.loc[
                n["tcgplayer_product_id"].isin(governed_ids)
                & n["parsed_date"].notna()
                & n["source_market_price"].gt(0)
            ].copy()
            rows.append(n)
        except Exception as exc:
            errors.append({"path": rel, "error_type": type(exc).__name__, "error_message": str(exc)[:500]})

    all_rows = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=[
        "tcgplayer_product_id", "source_observation_date", "source_market_price", "source_product_name",
        "parsed_date", "observation_month", "source_path", "source_precedence", "source_row_number"
    ])
    all_rows["governed_box_name"] = all_rows["tcgplayer_product_id"].map(name_map).fillna("")
    all_rows["release_state"] = all_rows["tcgplayer_product_id"].map(release_map).fillna("")

    key_counts = all_rows.groupby(["tcgplayer_product_id", "observation_month"]).size().reset_index(name="candidate_count") if len(all_rows) else pd.DataFrame(columns=["tcgplayer_product_id", "observation_month", "candidate_count"])
    duplicate_keys = key_counts.loc[key_counts["candidate_count"] > 1].copy()

    selected = all_rows.sort_values(["tcgplayer_product_id", "observation_month", "source_precedence", "source_row_number"]).drop_duplicates(["tcgplayer_product_id", "observation_month"], keep="first").copy()
    selected["history_lane"] = selected["release_state"].map(lambda x: "PRESALE_ISOLATED" if x == "PRESALE" else "RELEASED_MONTHLY_HISTORY_CANDIDATE")
    selected["historical_append_authorized"] = False

    released = selected.loc[~selected["release_state"].eq("PRESALE")].copy()
    presale = selected.loc[selected["release_state"].eq("PRESALE")].copy()

    coverage = released.groupby("tcgplayer_product_id").agg(
        selected_months=("observation_month", "nunique"),
        first_month=("observation_month", "min"),
        last_month=("observation_month", "max"),
    ).reset_index() if len(released) else pd.DataFrame(columns=["tcgplayer_product_id", "selected_months", "first_month", "last_month"])
    coverage["governed_box_name"] = coverage["tcgplayer_product_id"].map(name_map).fillna("")
    coverage["release_state"] = coverage["tcgplayer_product_id"].map(release_map).fillna("")
    missing = governed.loc[~governed["tcgplayer_product_id"].isin(set(coverage["tcgplayer_product_id"]))].copy()

    all_rows.to_csv(out / "collector_safe_monthly_source_rows.csv", index=False)
    selected.to_csv(out / "collector_safe_monthly_history_all.csv", index=False)
    released.to_csv(out / "collector_safe_released_monthly_history_candidate.csv", index=False)
    presale.to_csv(out / "collector_safe_presale_history_isolated.csv", index=False)
    duplicate_keys.to_csv(out / "collector_safe_monthly_duplicate_keys.csv", index=False)
    coverage.to_csv(out / "collector_safe_monthly_product_coverage.csv", index=False)
    missing.to_csv(out / "collector_safe_monthly_products_without_released_history.csv", index=False)
    pd.DataFrame(errors, columns=["path", "error_type", "error_message"]).to_csv(out / "collector_safe_monthly_history_errors.csv", index=False)

    summary = {
        "block_name": "Collector Safe Monthly History Candidate",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governed_products": int(len(governed)),
        "safe_monthly_sources": int(len(safe_paths)),
        "source_errors": int(len(errors)),
        "safe_source_rows": int(len(all_rows)),
        "selected_product_month_rows": int(len(selected)),
        "released_candidate_rows": int(len(released)),
        "presale_isolated_rows": int(len(presale)),
        "selected_products": int(selected["tcgplayer_product_id"].nunique()) if len(selected) else 0,
        "duplicate_product_month_keys": int(len(duplicate_keys)),
        "products_without_released_history": int(len(missing)),
        "listing_rows_used_as_monthly_market_price": 0,
        "arbitrary_first_row_selection_authorized": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_SAFE_MONTHLY_CANDIDATE_ONLY" if len(released) and not errors and not len(duplicate_keys) else "REVIEW_REQUIRED",
    }
    (out / "collector_safe_monthly_history_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and (errors or not len(released) or len(duplicate_keys)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
