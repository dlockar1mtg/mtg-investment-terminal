"""Audit Collector historical source grain before monthly price selection."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_historical_source_grain_policy_v1.json"
DEFAULT_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_current_authority/collector_current_authority_all.csv"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_historical_source_grain"

ID_COLS = ["tcgplayer_product_id", "product_id", "productId"]
DATE_COLS = ["observation_date", "date", "price_date", "month", "timestamp", "collected_at", "source_timestamp"]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Audit Collector historical source grain")
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def first_col(frame: pd.DataFrame, candidates: list[str]) -> str:
    lookup = {str(c).lower(): str(c) for c in frame.columns}
    return next((lookup[x.lower()] for x in candidates if x.lower() in lookup), "")


def norm_id(value: object) -> str:
    value = "" if pd.isna(value) else str(value).strip()
    return value[:-2] if value.endswith(".0") else value


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")


def main() -> int:
    args = parser().parse_args()
    policy = json.loads(args.policy.resolve().read_text(encoding="utf-8-sig"))
    authority = read_csv(args.authority.resolve())
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)
    governed_ids = set(authority.loc[authority["identity_authority_status"].eq("CURRENT_IDENTITY_AUTHORIZED"), "tcgplayer_product_id"])
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    audits: list[dict[str, object]] = []
    multiplicity_rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for spec in policy["known_source_roles"]:
        rel = spec["path"]
        path = ROOT / rel
        if not path.is_file():
            errors.append({"path": rel, "error_type": "FileNotFoundError", "error_message": "configured source missing"})
            continue
        try:
            frame = read_csv(path)
            id_col = first_col(frame, ID_COLS)
            date_col = first_col(frame, DATE_COLS)
            market_col = first_col(frame, policy["monthly_market_price_columns"])
            listing_col = first_col(frame, policy["listing_price_columns"])
            metadata_cols = [c for c in policy["source_metadata_columns"] if c in frame.columns]

            if id_col:
                ids = frame[id_col].map(norm_id)
                governed = ids.isin(governed_ids)
            else:
                ids = pd.Series([""] * len(frame), index=frame.index)
                governed = pd.Series([False] * len(frame), index=frame.index)

            parsed = pd.to_datetime(frame[date_col], errors="coerce", utc=True) if date_col else pd.Series(pd.NaT, index=frame.index)
            months = parsed.dt.strftime("%Y-%m-01")
            price_col = market_col or listing_col
            prices = pd.to_numeric(frame[price_col], errors="coerce") if price_col else pd.Series(pd.NA, index=frame.index, dtype="Float64")

            eligible = pd.DataFrame({
                "tcgplayer_product_id": ids,
                "observation_month": months,
                "price": prices,
            }).loc[governed & months.notna() & prices.gt(0)].copy()

            if len(eligible):
                grouped = eligible.groupby(["tcgplayer_product_id", "observation_month"]).agg(
                    row_count=("price", "size"),
                    distinct_price_count=("price", "nunique"),
                    minimum_price=("price", "min"),
                    maximum_price=("price", "max"),
                ).reset_index()
                grouped["source_path"] = rel
                grouped["absolute_spread"] = grouped["maximum_price"] - grouped["minimum_price"]
                multiplicity_rows.extend(grouped.to_dict("records"))
                duplicate_keys = int((grouped["row_count"] > 1).sum())
                max_rows_per_key = int(grouped["row_count"].max())
                one_row_share = float((grouped["row_count"] == 1).mean())
                distinct_price_conflicts = int((grouped["distinct_price_count"] > 1).sum())
            else:
                duplicate_keys = 0
                max_rows_per_key = 0
                one_row_share = 0.0
                distinct_price_conflicts = 0

            if not price_col:
                observed_role = "NON_PRICE_LEDGER"
            elif len(eligible) and one_row_share >= 0.98 and max_rows_per_key <= 2:
                observed_role = "MONTHLY_MARKET_HISTORY_CANDIDATE"
            elif len(eligible) and max_rows_per_key > 2:
                observed_role = "LISTING_OR_MIXED_GRAIN_EVIDENCE"
            else:
                observed_role = "REVIEW_REQUIRED"

            audits.append({
                "path": rel,
                "expected_role": spec["expected_role"],
                "observed_role": observed_role,
                "source_rows": int(len(frame)),
                "column_count": int(len(frame.columns)),
                "identity_column": id_col,
                "date_column": date_col,
                "market_price_column": market_col,
                "listing_price_column": listing_col,
                "metadata_columns": ";".join(metadata_cols),
                "governed_eligible_rows": int(len(eligible)),
                "product_month_keys": int(len(grouped)) if len(eligible) else 0,
                "duplicate_product_month_keys": duplicate_keys,
                "distinct_price_conflict_keys": distinct_price_conflicts,
                "maximum_rows_per_product_month": max_rows_per_key,
                "one_row_per_product_month_share": round(one_row_share, 6),
                "safe_for_monthly_market_selection": observed_role == "MONTHLY_MARKET_HISTORY_CANDIDATE",
            })
        except Exception as exc:
            errors.append({"path": rel, "error_type": type(exc).__name__, "error_message": str(exc)[:500]})

    audit_df = pd.DataFrame(audits)
    mult_df = pd.DataFrame(multiplicity_rows)
    error_df = pd.DataFrame(errors, columns=["path", "error_type", "error_message"])
    audit_df.to_csv(out / "collector_historical_source_grain_audit.csv", index=False)
    mult_df.to_csv(out / "collector_historical_product_month_multiplicity.csv", index=False)
    error_df.to_csv(out / "collector_historical_source_grain_errors.csv", index=False)

    safe_sources = audit_df.loc[audit_df.get("safe_for_monthly_market_selection", False).eq(True)].copy() if len(audit_df) else pd.DataFrame()
    listing_sources = audit_df.loc[audit_df.get("observed_role", "").eq("LISTING_OR_MIXED_GRAIN_EVIDENCE")].copy() if len(audit_df) else pd.DataFrame()
    safe_sources.to_csv(out / "collector_historical_safe_monthly_sources.csv", index=False)
    listing_sources.to_csv(out / "collector_historical_listing_evidence_sources.csv", index=False)

    summary = {
        "audit_name": "Collector Historical Source Grain Audit",
        "audit_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configured_sources": len(policy["known_source_roles"]),
        "sources_audited": int(len(audit_df)),
        "source_errors": int(len(error_df)),
        "safe_monthly_sources": int(len(safe_sources)),
        "listing_or_mixed_sources": int(len(listing_sources)),
        "arbitrary_first_row_selection_authorized": False,
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_SOURCE_GRAIN_AUDIT" if len(safe_sources) and not len(error_df) else "REVIEW_REQUIRED",
    }
    (out / "collector_historical_source_grain_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and (len(error_df) or not len(safe_sources)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
