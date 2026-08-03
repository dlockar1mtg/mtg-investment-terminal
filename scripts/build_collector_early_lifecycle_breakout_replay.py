from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_early_lifecycle_breakout_replay_v1.json"
OUTCOME_CANDIDATES = [
    ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0/collector_walk_forward_phase_2a_scored_outcomes.csv",
    ROOT / "data/operations/collector_365_direct_comparable_tournament/candidate_v1_0_0/collector_365_direct_predictions.csv",
]


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


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
    top_n = max(1, int(math.ceil(len(frame) * 0.20))) if len(frame) else 0
    top_ids = set(frame.nlargest(top_n, "forecast_signal").index) if top_n else set()
    for threshold in thresholds:
        tag = int(round(threshold * 100))
        actual = frame["realized_return_365"] >= threshold
        predicted = frame["forecast_signal"] >= threshold
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
    feature_path = ROOT / cfg["inputs"]["historical_feature_panel"]
    out = ROOT / cfg["output_root"]
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    features = read_csv(feature_path)
    outcomes = next((read_csv(path) for path in OUTCOME_CANDIDATES if not read_csv(path).empty), pd.DataFrame())
    if features.empty:
        failures.append("historical_feature_panel_missing_or_empty")
    if outcomes.empty:
        failures.append("validated_365_outcome_source_missing_or_empty")

    fname = choose(features, ["product_name", "canonical_product_name", "name"])
    fcut = choose(features, ["decision_cutoff", "cutoff_date", "as_of_date"])
    fid = choose(features, ["tcgplayer_product_id", "product_key", "canonical_product_id"])
    frelease = choose(features, ["release_date", "published_on", "set_release_date"])
    fage = choose(features, ["product_age_months", "age_months", "months_since_release", "product_age_months_at_cutoff"])
    oname = choose(outcomes, ["product_name", "canonical_product_name", "name"])
    ocut = choose(outcomes, ["decision_cutoff", "cutoff_date", "as_of_date"])
    oid = choose(outcomes, ["tcgplayer_product_id", "product_key", "canonical_product_id"])
    ohorizon = choose(outcomes, ["horizon_days", "forecast_horizon_days", "horizon"])
    orealized = choose(outcomes, [
        "realized_return_365", "forward_return_365", "actual_return_365", "target_return_365",
        "realized_return", "actual_return", "forward_return", "outcome_return",
    ])

    diagnostics = {
        "feature_rows": int(len(features)), "outcome_rows": int(len(outcomes)),
        "feature_name_column": fname or "UNMAPPED", "feature_cutoff_column": fcut or "UNMAPPED",
        "feature_id_column": fid or "UNMAPPED", "feature_age_column": fage or "DERIVED_FROM_RELEASE_DATE",
        "feature_release_column": frelease or "UNMAPPED", "outcome_name_column": oname or "UNMAPPED",
        "outcome_cutoff_column": ocut or "UNMAPPED", "outcome_id_column": oid or "UNMAPPED",
        "outcome_horizon_column": ohorizon or "UNMAPPED", "outcome_realized_column": orealized or "UNMAPPED",
        "feature_columns": "|".join(map(str, features.columns)),
        "outcome_columns": "|".join(map(str, outcomes.columns)),
    }
    pd.DataFrame([diagnostics]).to_csv(out / "collector_early_lifecycle_breakout_replay_schema_diagnostics.csv", index=False)

    if fname is None or fcut is None:
        failures.append("feature_identity_or_cutoff_unmapped")
    if oname is None or ocut is None or orealized is None:
        failures.append("outcome_identity_cutoff_or_realized_unmapped")

    replay = pd.DataFrame()
    if not failures:
        feature_cutoff = pd.to_datetime(features[fcut], errors="coerce")
        if fage:
            age = pd.to_numeric(features[fage], errors="coerce")
        elif frelease:
            release = pd.to_datetime(features[frelease], errors="coerce")
            age = ((feature_cutoff.dt.year - release.dt.year) * 12 + feature_cutoff.dt.month - release.dt.month).astype(float)
        else:
            age = pd.Series(np.nan, index=features.index, dtype=float)

        feature_frame = pd.DataFrame({
            "join_id": features[fid].map(clean_id) if fid else features[fname].astype(str).str.lower().str.strip(),
            "product_key": features[fid].map(clean_id) if fid else features[fname].astype(str),
            "product_name": features[fname].astype(str),
            "decision_cutoff": feature_cutoff,
            "product_age_months": age,
            "return_3_month": numeric(features, ["return_3_month", "return_90d", "return_3m", "trailing_return_3_month"]),
            "return_6_month": numeric(features, ["return_6_month", "return_180d", "return_6m", "trailing_return_6_month"]),
            "return_12_month_at_cutoff": numeric(features, ["return_12_month", "return_365d", "return_12m", "trailing_return_12_month"]),
        })
        outcome_frame = pd.DataFrame({
            "join_id": outcomes[oid].map(clean_id) if oid else outcomes[oname].astype(str).str.lower().str.strip(),
            "decision_cutoff": pd.to_datetime(outcomes[ocut], errors="coerce"),
            "realized_return_365": pd.to_numeric(outcomes[orealized], errors="coerce"),
        })
        if ohorizon:
            horizon = pd.to_numeric(outcomes[ohorizon], errors="coerce")
            outcome_frame = outcome_frame.loc[horizon.eq(365)].copy()
        outcome_frame = outcome_frame.dropna(subset=["decision_cutoff", "realized_return_365"]).drop_duplicates(["join_id", "decision_cutoff"])
        replay = feature_frame.merge(outcome_frame, on=["join_id", "decision_cutoff"], how="inner")
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

    case_columns = [
        "product_key", "product_name", "decision_cutoff", "product_age_months", "early_lifecycle_band",
        "return_3_month", "return_6_month", "return_12_month_at_cutoff", "forecast_signal",
        "realized_return_365", "future_information_used_in_forecast", "historical_outcome_used_for_scoring_only",
    ]
    replay.reindex(columns=case_columns).to_csv(out / "collector_early_lifecycle_breakout_replay_cases.csv", index=False)
    pd.DataFrame(summary_rows, columns=["scope", *cfg["required_metrics"]]).to_csv(
        out / "collector_early_lifecycle_breakout_replay_summary.csv", index=False
    )

    result = {
        "audit_name": cfg["program_name"], "audit_version": "1.1.0",
        "status": "PASS" if not failures else "FAIL", "case_count": int(len(replay)),
        "product_count": int(replay["product_key"].nunique()) if not replay.empty else 0,
        "cutoff_count": int(replay["decision_cutoff"].nunique()) if not replay.empty else 0,
        "age_band_count": int(replay["early_lifecycle_band"].nunique()) if not replay.empty else 0,
        "feature_outcome_join_contract": "AT_CUTOFF_FEATURES_PLUS_VALIDATED_365_OUTCOME",
        "future_information_used_in_forecast": False, "historical_outcome_used_for_scoring_only": True,
        "methodology_change_authorized": False, "production_projection_authorized": False,
        "purchase_recommendation_authorized": False, "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False, "uip_acceptance_authorized": False,
        "failure_count": len(failures), "failures": failures,
    }
    (out / "collector_early_lifecycle_breakout_replay_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
