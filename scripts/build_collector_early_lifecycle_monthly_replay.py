from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_early_lifecycle_monthly_replay_v1.json"


def choose(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lower = {str(c).lower(): str(c) for c in df.columns}
    return next((lower[a.lower()] for a in aliases if a.lower() in lower), None)


def clean_id(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def age_band(age: float) -> str:
    if not math.isfinite(age) or age < 0 or age > 17:
        return "OUT_OF_SCOPE"
    if age <= 3:
        return "LAUNCH_PRICE_DISCOVERY"
    if age <= 8:
        return "INITIAL_SUPPLY_ABSORPTION"
    if age <= 12:
        return "STABILIZATION"
    return "EARLY_ACCUMULATION"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    source = ROOT / cfg["inputs"]["monthly_price_panel"]
    out = ROOT / cfg["output_root"]
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    try:
        raw = pd.read_csv(source, low_memory=False)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        raw = pd.DataFrame()
    if raw.empty:
        failures.append("monthly_price_panel_missing_or_empty")

    name_col = choose(raw, ["product_name", "canonical_product_name", "name", "box_name"])
    id_col = choose(raw, ["tcgplayer_product_id", "product_key", "canonical_product_id"])
    date_col = choose(raw, ["observation_month", "month", "observation_date", "price_date", "date", "as_of_date"])
    release_col = choose(raw, ["release_date", "published_on", "set_release_date"])
    price_col = choose(raw, ["market_price", "price", "monthly_price", "current_price", "value"])
    required_map = {
        "product_name": name_col,
        "observation_date": date_col,
        "release_date": release_col,
        "market_price": price_col,
    }
    for label, column in required_map.items():
        if column is None:
            failures.append(f"{label}_unmapped")

    cases = pd.DataFrame()
    if not failures:
        work = pd.DataFrame({
            "product_key": raw[id_col].map(clean_id) if id_col else raw[name_col].astype(str),
            "product_name": raw[name_col].astype(str).str.strip(),
            "observation_date": pd.to_datetime(raw[date_col], errors="coerce"),
            "release_date": pd.to_datetime(raw[release_col], errors="coerce"),
            "market_price": pd.to_numeric(raw[price_col], errors="coerce"),
        }).dropna(subset=["observation_date", "release_date", "market_price"])
        work = work[work["market_price"] > 0].copy()
        work = work.sort_values(["product_key", "observation_date"]).drop_duplicates(["product_key", "observation_date"], keep="last")
        work["product_age_months"] = (
            (work["observation_date"].dt.year - work["release_date"].dt.year) * 12
            + (work["observation_date"].dt.month - work["release_date"].dt.month)
        ).astype(float)
        work["early_lifecycle_band"] = work["product_age_months"].map(age_band)
        work = work[work["early_lifecycle_band"] != "OUT_OF_SCOPE"].copy()

        rows: list[dict[str, object]] = []
        min_gap = int(cfg["minimum_forward_gap_months"])
        max_gap = int(cfg["maximum_forward_gap_months"])
        for product_key, group in work.groupby("product_key", dropna=False):
            group = group.sort_values("observation_date").reset_index(drop=True)
            for _, row in group.iterrows():
                gaps = (
                    (group["observation_date"].dt.year - row["observation_date"].year) * 12
                    + (group["observation_date"].dt.month - row["observation_date"].month)
                )
                future = group[(gaps >= min_gap) & (gaps <= max_gap)].copy()
                if future.empty:
                    continue
                future["gap_distance"] = (gaps.loc[future.index] - int(cfg["forward_horizon_months"])).abs()
                target = future.sort_values(["gap_distance", "observation_date"]).iloc[0]
                realized = float(target["market_price"] / row["market_price"] - 1.0)
                rows.append({
                    "product_key": clean_id(product_key),
                    "product_name": row["product_name"],
                    "decision_cutoff": row["observation_date"].date().isoformat(),
                    "release_date": row["release_date"].date().isoformat(),
                    "product_age_months": int(row["product_age_months"]),
                    "early_lifecycle_band": row["early_lifecycle_band"],
                    "current_price_at_cutoff": float(row["market_price"]),
                    "forward_observation_date": target["observation_date"].date().isoformat(),
                    "forward_gap_months": int((target["observation_date"].year - row["observation_date"].year) * 12 + (target["observation_date"].month - row["observation_date"].month)),
                    "forward_price_365": float(target["market_price"]),
                    "realized_return_365": realized,
                    "breakout_25": realized >= 0.25,
                    "breakout_50": realized >= 0.50,
                    "breakout_70": realized >= 0.70,
                    "future_information_used_in_features": False,
                    "forward_price_used_for_scoring_only": True,
                })
        cases = pd.DataFrame(rows)

    if cases.empty:
        failures.append("no_monthly_early_lifecycle_cases")

    cases.to_csv(out / "collector_early_lifecycle_monthly_replay_cases.csv", index=False)
    diagnostics = pd.DataFrame([{
        "source_rows": int(len(raw)),
        "name_column": name_col or "UNMAPPED",
        "id_column": id_col or "UNMAPPED",
        "date_column": date_col or "UNMAPPED",
        "release_column": release_col or "UNMAPPED",
        "price_column": price_col or "UNMAPPED",
    }])
    diagnostics.to_csv(out / "collector_early_lifecycle_monthly_replay_schema_diagnostics.csv", index=False)

    outcome_counts = {
        "negative_return_count": int((cases["realized_return_365"] < 0).sum()) if not cases.empty else 0,
        "below_25_count": int((cases["realized_return_365"] < 0.25).sum()) if not cases.empty else 0,
        "breakout_25_count": int((cases["realized_return_365"] >= 0.25).sum()) if not cases.empty else 0,
        "breakout_50_count": int((cases["realized_return_365"] >= 0.50).sum()) if not cases.empty else 0,
        "breakout_70_count": int((cases["realized_return_365"] >= 0.70).sum()) if not cases.empty else 0,
    }
    result = {
        "audit_name": cfg["program_name"],
        "audit_version": cfg["program_version"],
        "case_count": int(len(cases)),
        "product_count": int(cases["product_key"].nunique()) if not cases.empty else 0,
        "cutoff_count": int(cases["decision_cutoff"].nunique()) if not cases.empty else 0,
        "age_band_count": int(cases["early_lifecycle_band"].nunique()) if not cases.empty else 0,
        **outcome_counts,
        "future_information_used_in_features": False,
        "forward_price_used_for_scoring_only": True,
        "complete_negative_case_retention_required": True,
        "methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    (out / "collector_early_lifecycle_monthly_replay_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
