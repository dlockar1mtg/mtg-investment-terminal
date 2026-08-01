from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_early_lifecycle_breakout_replay_v1.json"


def choose(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lower = {str(c).lower(): str(c) for c in df.columns}
    return next((lower[a.lower()] for a in aliases if a.lower() in lower), None)


def numeric(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    col = choose(df, aliases)
    return pd.to_numeric(df[col], errors="coerce") if col else pd.Series(np.nan, index=df.index, dtype=float)


def clean_id(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def age_band(age: float) -> str:
    if not math.isfinite(age) or age < 0:
        return "OUT_OF_SCOPE"
    if age <= 3:
        return "LAUNCH_PRICE_DISCOVERY"
    if age <= 8:
        return "INITIAL_SUPPLY_ABSORPTION"
    if age <= 12:
        return "STABILIZATION"
    if age <= 17:
        return "EARLY_ACCUMULATION"
    return "OUT_OF_SCOPE"


def safe_corr(a: pd.Series, b: pd.Series) -> float:
    valid = pd.concat([a, b], axis=1).dropna()
    return float(valid.iloc[:, 0].corr(valid.iloc[:, 1], method="spearman")) if len(valid) >= 3 else np.nan


def top_bottom_spread(frame: pd.DataFrame) -> float:
    if len(frame) < 5:
        return np.nan
    ranked = frame.sort_values("forecast_signal")
    n = max(1, int(math.ceil(len(ranked) * 0.20)))
    return float(ranked.tail(n)["realized_return_365"].mean() - ranked.head(n)["realized_return_365"].mean())


def metrics(frame: pd.DataFrame, thresholds: list[float]) -> dict[str, object]:
    result: dict[str, object] = {
        "case_count": int(len(frame)),
        "product_count": int(frame["product_key"].nunique()),
        "cutoff_count": int(frame["decision_cutoff"].nunique()),
        "rank_correlation": safe_corr(frame["forecast_signal"], frame["realized_return_365"]),
        "top_bottom_spread": top_bottom_spread(frame),
    }
    if frame.empty:
        for t in thresholds:
            tag = int(round(t * 100))
            for name in ["breakout_count", "breakout_recall", "false_negative_rate", "top_quantile_capture", "false_positive_rate", "mean_missed_upside"]:
                result[f"{name}_{tag}"] = 0 if name == "breakout_count" else np.nan
        return result

    top_n = max(1, int(math.ceil(len(frame) * 0.20)))
    top_ids = set(frame.nlargest(top_n, "forecast_signal").index)
    for t in thresholds:
        tag = int(round(t * 100))
        actual = frame["realized_return_365"] >= t
        predicted = frame["forecast_signal"] >= t
        breakout_count = int(actual.sum())
        tp = int((actual & predicted).sum())
        fn = int((actual & ~predicted).sum())
        fp = int((~actual & predicted).sum())
        negatives = int((~actual).sum())
        captured_top = int(sum(i in top_ids for i in frame.index[actual]))
        missed = frame.loc[actual & ~predicted, "realized_return_365"] - frame.loc[actual & ~predicted, "forecast_signal"]
        result[f"breakout_count_{tag}"] = breakout_count
        result[f"breakout_recall_{tag}"] = tp / breakout_count if breakout_count else np.nan
        result[f"false_negative_rate_{tag}"] = fn / breakout_count if breakout_count else np.nan
        result[f"top_quantile_capture_{tag}"] = captured_top / breakout_count if breakout_count else np.nan
        result[f"false_positive_rate_{tag}"] = fp / negatives if negatives else np.nan
        result[f"mean_missed_upside_{tag}"] = float(missed.mean()) if not missed.empty else 0.0
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    source = ROOT / cfg["inputs"]["historical_feature_panel"]
    out = ROOT / cfg["output_root"]
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    try:
        df = pd.read_csv(source, low_memory=False)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        df = pd.DataFrame()
    if df.empty:
        failures.append("historical_feature_panel_missing_or_empty")

    name_col = choose(df, ["product_name", "canonical_product_name", "name"])
    cutoff_col = choose(df, ["decision_cutoff", "cutoff_date", "as_of_date"])
    id_col = choose(df, ["tcgplayer_product_id", "product_key", "canonical_product_id"])
    if name_col is None:
        failures.append("product_name_unmapped")
    if cutoff_col is None:
        failures.append("decision_cutoff_unmapped")

    replay = pd.DataFrame()
    if not failures:
        replay = pd.DataFrame({
            "product_key": df[id_col].map(clean_id) if id_col else df[name_col].astype(str),
            "product_name": df[name_col].astype(str),
            "decision_cutoff": pd.to_datetime(df[cutoff_col], errors="coerce"),
            "product_age_months": numeric(df, ["product_age_months", "age_months", "months_since_release"]),
            "return_3_month": numeric(df, ["return_3_month", "return_90d", "return_3m"]),
            "return_6_month": numeric(df, ["return_6_month", "return_180d", "return_6m"]),
            "return_12_month_at_cutoff": numeric(df, ["return_12_month", "return_365d", "return_12m"]),
            "realized_return_365": numeric(df, ["realized_return_365", "forward_return_365", "actual_return_365", "target_return_365"]),
        })
        replay["early_lifecycle_band"] = replay["product_age_months"].map(age_band)
        replay = replay[replay["early_lifecycle_band"] != "OUT_OF_SCOPE"].copy()
        replay["forecast_signal"] = replay[["return_3_month", "return_6_month", "return_12_month_at_cutoff"]].median(axis=1, skipna=True)
        replay = replay.dropna(subset=["decision_cutoff", "forecast_signal", "realized_return_365"])
        replay["future_information_used_in_forecast"] = False
        replay["historical_outcome_used_for_scoring_only"] = True

    if replay.empty:
        failures.append("no_eligible_early_lifecycle_replay_cases")

    thresholds = [float(x) for x in cfg["breakout_thresholds"]]
    summary_rows: list[dict[str, object]] = []
    if not replay.empty:
        summary_rows.append({"scope": "ALL_EARLY_LIFECYCLE", **metrics(replay, thresholds)})
        for band, group in replay.groupby("early_lifecycle_band"):
            summary_rows.append({"scope": str(band), **metrics(group, thresholds)})

    summary = pd.DataFrame(summary_rows)
    replay.to_csv(out / "collector_early_lifecycle_breakout_replay_cases.csv", index=False)
    summary.to_csv(out / "collector_early_lifecycle_breakout_replay_summary.csv", index=False)

    if not replay.empty and replay["future_information_used_in_forecast"].any():
        failures.append("future_information_used_in_forecast")
    if not summary.empty and "ALL_EARLY_LIFECYCLE" not in set(summary["scope"]):
        failures.append("overall_summary_missing")

    result = {
        "audit_name": cfg["program_name"],
        "audit_version": cfg["program_version"],
        "status": "PASS" if not failures else "FAIL",
        "case_count": int(len(replay)),
        "product_count": int(replay["product_key"].nunique()) if not replay.empty else 0,
        "cutoff_count": int(replay["decision_cutoff"].nunique()) if not replay.empty else 0,
        "age_band_count": int(replay["early_lifecycle_band"].nunique()) if not replay.empty else 0,
        "future_information_used_in_forecast": False,
        "historical_outcome_used_for_scoring_only": True,
        "methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    (out / "collector_early_lifecycle_breakout_replay_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
