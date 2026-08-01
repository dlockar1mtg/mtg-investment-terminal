"""Certify a controlled live TCGCSV Collector current-price pull.

This script compares the fresh governed pull with the previously governed
current authority. It preserves valid high prices, isolates presale products,
and never appends to historical data.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRESH = ROOT / "data/operations/tcgcsv/collector_live_price_observations.csv"
DEFAULT_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_current_authority/collector_current_authority_all.csv"
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_current_authority_policy_v1.json"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_live_current_prices"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Certify live Collector current-price continuity")
    p.add_argument("--fresh-observations", type=Path, default=DEFAULT_FRESH)
    p.add_argument("--current-authority", type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--strict", action="store_true")
    return p


def text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_id(value: object) -> str:
    raw = text(value)
    return raw[:-2] if raw.endswith(".0") else raw


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def main() -> int:
    args = parser().parse_args()
    fresh_path = args.fresh_observations.resolve()
    authority_path = args.current_authority.resolve()
    policy_path = args.policy.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for label, path in (("fresh_observations", fresh_path), ("current_authority", authority_path), ("policy", policy_path)):
        if not path.is_file():
            failures.append(f"{label}_missing")

    if failures:
        summary = {
            "audit_name": "Collector Live Current Price Certification",
            "audit_version": "1.0.0",
            "status": "FAIL",
            "failures": failures,
            "historical_append_authorized": False,
            "forecasting_resume_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        (out / "collector_live_current_price_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    fresh = pd.read_csv(fresh_path, dtype=str).fillna("")
    authority = pd.read_csv(authority_path, dtype=str).fillna("")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))

    required_fresh = {
        "box_name", "tcgplayer_product_id", "market_price",
        "price_selection_status", "normal_subtype_row_count",
        "raw_sha256", "raw_vault_path", "retrieval_id",
    }
    required_authority = {
        "tcgplayer_product_id", "box_name", "market_price",
        "release_state", "identity_authority_status",
    }
    missing_fresh = sorted(required_fresh - set(fresh.columns))
    missing_authority = sorted(required_authority - set(authority.columns))
    if missing_fresh:
        failures.append("fresh_schema_missing:" + ",".join(missing_fresh))
    if missing_authority:
        failures.append("authority_schema_missing:" + ",".join(missing_authority))
    if failures:
        summary = {
            "audit_name": "Collector Live Current Price Certification",
            "audit_version": "1.0.0",
            "status": "FAIL",
            "failures": failures,
            "historical_append_authorized": False,
            "forecasting_resume_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        (out / "collector_live_current_price_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 1

    fresh["tcgplayer_product_id"] = fresh["tcgplayer_product_id"].map(norm_id)
    authority["tcgplayer_product_id"] = authority["tcgplayer_product_id"].map(norm_id)
    fresh["fresh_market_price"] = numeric(fresh["market_price"])
    authority["prior_market_price"] = numeric(authority["market_price"])

    duplicate_fresh_ids = sorted(
        fresh.groupby("tcgplayer_product_id").size().loc[lambda s: s > 1].index.tolist()
    )
    fresh_unique = fresh.loc[~fresh["tcgplayer_product_id"].isin(duplicate_fresh_ids)].copy()

    authority_cols = [
        "tcgplayer_product_id", "box_name", "prior_market_price",
        "release_state", "identity_authority_status",
    ]
    merged = authority[authority_cols].merge(
        fresh_unique,
        on="tcgplayer_product_id",
        how="left",
        suffixes=("_authority", "_fresh"),
        validate="one_to_one",
    )

    attested = {
        str(row["tcgplayer_product_id"]): float(row["market_price"])
        for row in policy["price_policy"].get("owner_attested_current_prices", [])
    }

    merged["absolute_change"] = merged["fresh_market_price"] - merged["prior_market_price"]
    merged["change_ratio"] = np.where(
        merged["prior_market_price"] > 0,
        merged["fresh_market_price"] / merged["prior_market_price"],
        np.nan,
    )
    merged["percent_change"] = np.where(
        merged["prior_market_price"] > 0,
        (merged["fresh_market_price"] / merged["prior_market_price"] - 1.0) * 100.0,
        np.nan,
    )

    def classify(row: pd.Series) -> pd.Series:
        pid = text(row.get("tcgplayer_product_id"))
        reasons: list[str] = []
        warnings: list[str] = []

        if pid in duplicate_fresh_ids:
            reasons.append("DUPLICATE_FRESH_PRODUCT_ID")
        if text(row.get("identity_authority_status")) != "CURRENT_IDENTITY_AUTHORIZED":
            reasons.append("IDENTITY_NOT_AUTHORIZED")
        if pd.isna(row.get("fresh_market_price")) or float(row.get("fresh_market_price")) <= 0:
            reasons.append("FRESH_MARKET_PRICE_MISSING_OR_NONPOSITIVE")
        if text(row.get("price_selection_status")) != "NORMAL_SUBTYPE_UNIQUE":
            reasons.append("NORMAL_SUBTYPE_NOT_UNIQUE")
        if text(row.get("normal_subtype_row_count")) != "1":
            reasons.append("NORMAL_SUBTYPE_COUNT_NOT_ONE")
        if not text(row.get("retrieval_id")):
            reasons.append("RETRIEVAL_ID_MISSING")
        if not text(row.get("raw_sha256")):
            reasons.append("RAW_HASH_MISSING")
        if not text(row.get("raw_vault_path")):
            reasons.append("RAW_VAULT_PATH_MISSING")

        ratio = row.get("change_ratio")
        if pd.notna(ratio):
            ratio = float(ratio)
            if ratio < 0.50 or ratio > 2.00:
                warnings.append("EXTREME_CONTINUITY_CHANGE_REVIEW")
            elif ratio < 0.75 or ratio > 1.25:
                warnings.append("MATERIAL_CONTINUITY_CHANGE_REVIEW")

        owner_value = attested.get(pid)
        if owner_value is not None:
            warnings.append("OWNER_ATTESTED_HIGH_VALUE_PRODUCT")

        release_state = text(row.get("release_state"))
        if release_state == "PRESALE":
            warnings.append("PRESALE_ISOLATION_REQUIRED")

        status = "CURRENT_PRICE_CERTIFIED_CANDIDATE" if not reasons else "QUARANTINED"
        append_eligible = status == "CURRENT_PRICE_CERTIFIED_CANDIDATE" and release_state != "PRESALE"
        return pd.Series({
            "certification_status": status,
            "historical_append_candidate": bool(append_eligible),
            "blocking_reasons": ";".join(reasons),
            "review_warnings": ";".join(warnings),
            "owner_attested_reference_price": owner_value if owner_value is not None else "",
        })

    reviewed = merged.join(merged.apply(classify, axis=1))
    certified = reviewed.loc[reviewed["certification_status"].eq("CURRENT_PRICE_CERTIFIED_CANDIDATE")].copy()
    quarantine = reviewed.loc[reviewed["certification_status"].eq("QUARANTINED")].copy()
    presale = certified.loc[certified["release_state"].eq("PRESALE")].copy()
    nonpresale_candidates = certified.loc[~certified["release_state"].eq("PRESALE")].copy()
    continuity_review = certified.loc[certified["review_warnings"].str.contains("CONTINUITY", na=False)].copy()

    reviewed.to_csv(out / "collector_live_current_price_all.csv", index=False)
    certified.to_csv(out / "collector_live_current_price_certified_candidates.csv", index=False)
    quarantine.to_csv(out / "collector_live_current_price_quarantine.csv", index=False)
    presale.to_csv(out / "collector_live_current_price_presale.csv", index=False)
    nonpresale_candidates.to_csv(out / "collector_live_current_price_nonpresale_append_candidates.csv", index=False)
    continuity_review.to_csv(out / "collector_live_current_price_continuity_review.csv", index=False)

    missing_fresh_count = int(reviewed["fresh_market_price"].isna().sum())
    summary = {
        "audit_name": "Collector Live Current Price Certification",
        "audit_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority_rows": int(len(authority)),
        "fresh_rows": int(len(fresh)),
        "duplicate_fresh_product_id_count": int(len(duplicate_fresh_ids)),
        "missing_fresh_product_count": missing_fresh_count,
        "certified_candidate_rows": int(len(certified)),
        "quarantined_rows": int(len(quarantine)),
        "presale_rows": int(len(presale)),
        "nonpresale_append_candidate_rows": int(len(nonpresale_candidates)),
        "continuity_review_rows": int(len(continuity_review)),
        "historical_append_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS_CURRENT_PRICE_CANDIDATES_ONLY" if len(certified) == len(authority) and not duplicate_fresh_ids else "REVIEW_REQUIRED",
        "failures": [],
    }
    (out / "collector_live_current_price_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if args.strict and summary["status"] != "PASS_CURRENT_PRICE_CANDIDATES_ONLY":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
