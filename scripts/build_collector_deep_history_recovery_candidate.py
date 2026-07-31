from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_deep_history_recovery_candidate_v1.json"

ID_COLUMNS = ["tcgplayer_product_id", "approved_tcgplayer_product_id", "source_product_id"]
DATE_COLUMNS = ["observation_date", "snapshot_date", "date", "period", "month", "observed_at_utc", "latest_observation_date"]
PRICE_COLUMNS = ["market_price", "current_price", "price", "mid_price", "low_price", "high_price"]
NAME_COLUMNS = ["canonical_product_name", "product_name", "box_name", "official_product_name", "source_product_name"]
RELEASE_COLUMNS = ["release_date", "governed_release_date", "final_release_date_assigned", "published_on"]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_id(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        number = float(text)
        if math.isfinite(number) and number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def first_existing(columns: Iterable[str], candidates: list[str]) -> str | None:
    available = set(columns)
    return next((c for c in candidates if c in available), None)


def parse_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def read_csv(path: Path) -> tuple[pd.DataFrame | None, str | None]:
    try:
        return pd.read_csv(path, low_memory=False), None
    except Exception as exc:  # diagnostic batch must surface failures
        return None, f"{type(exc).__name__}: {exc}"


def build_release_map(cfg: dict) -> tuple[pd.DataFrame, list[dict]]:
    candidates: list[pd.DataFrame] = []
    source_rows: list[dict] = []
    for priority, rel in enumerate(cfg["release_sources"], start=1):
        path = ROOT / rel
        if not path.exists():
            source_rows.append({"path": rel, "role": "RELEASE", "exists": False, "readable": False, "error": "MISSING"})
            continue
        df, error = read_csv(path)
        source_rows.append({"path": rel, "role": "RELEASE", "exists": True, "readable": error is None, "error": error or ""})
        if df is None:
            continue
        id_col = first_existing(df.columns, ID_COLUMNS)
        release_col = first_existing(df.columns, RELEASE_COLUMNS)
        name_col = first_existing(df.columns, NAME_COLUMNS)
        if id_col is None:
            continue
        tmp = pd.DataFrame({
            "canonical_tcgplayer_product_id": df[id_col].map(normalize_id),
            "candidate_product_name": df[name_col].astype("string") if name_col else pd.Series([pd.NA] * len(df), dtype="string"),
            "candidate_release_date": parse_date_series(df[release_col]).dt.date.astype("string") if release_col else pd.Series([pd.NA] * len(df), dtype="string"),
            "release_source": rel,
            "release_source_priority": priority,
        })
        candidates.append(tmp.dropna(subset=["canonical_tcgplayer_product_id"]))

    for rel in cfg["admission_sources"]:
        path = ROOT / rel
        if not path.exists():
            source_rows.append({"path": rel, "role": "ADMISSION", "exists": False, "readable": False, "error": "MISSING"})
            continue
        df, error = read_csv(path)
        source_rows.append({"path": rel, "role": "ADMISSION", "exists": True, "readable": error is None, "error": error or ""})
        if df is None:
            continue
        id_col = first_existing(df.columns, ID_COLUMNS)
        if id_col is None:
            continue
        name_col = first_existing(df.columns, NAME_COLUMNS)
        release_col = first_existing(df.columns, RELEASE_COLUMNS)
        tmp = pd.DataFrame({
            "canonical_tcgplayer_product_id": df[id_col].map(normalize_id),
            "candidate_product_name": df[name_col].astype("string") if name_col else pd.Series([pd.NA] * len(df), dtype="string"),
            "candidate_release_date": parse_date_series(df[release_col]).dt.date.astype("string") if release_col else pd.Series([pd.NA] * len(df), dtype="string"),
            "release_source": rel,
            "release_source_priority": 999,
        })
        candidates.append(tmp.dropna(subset=["canonical_tcgplayer_product_id"]))

    if not candidates:
        return pd.DataFrame(columns=["canonical_tcgplayer_product_id", "product_name", "release_date", "release_source"]), source_rows
    all_candidates = pd.concat(candidates, ignore_index=True)
    all_candidates["has_name"] = all_candidates["candidate_product_name"].fillna("").str.strip().ne("")
    all_candidates["has_release"] = all_candidates["candidate_release_date"].fillna("").str.strip().ne("")
    all_candidates = all_candidates.sort_values(
        ["canonical_tcgplayer_product_id", "has_release", "has_name", "release_source_priority"],
        ascending=[True, False, False, True],
    )
    resolved = all_candidates.groupby("canonical_tcgplayer_product_id", as_index=False).first()
    resolved = resolved.rename(columns={"candidate_product_name": "product_name", "candidate_release_date": "release_date"})
    return resolved[["canonical_tcgplayer_product_id", "product_name", "release_date", "release_source"]], source_rows


def profile_and_normalize_history(path: Path, rel: str, governed_ids: set[str]) -> tuple[pd.DataFrame, dict]:
    if not path.exists():
        return pd.DataFrame(), {"path": rel, "exists": False, "readable": False, "error": "MISSING"}
    df, error = read_csv(path)
    if df is None:
        return pd.DataFrame(), {"path": rel, "exists": True, "readable": False, "error": error or "UNREADABLE"}
    id_col = first_existing(df.columns, ID_COLUMNS)
    date_col = first_existing(df.columns, DATE_COLUMNS)
    price_col = first_existing(df.columns, PRICE_COLUMNS)
    name_col = first_existing(df.columns, NAME_COLUMNS)
    normalized = pd.DataFrame()
    normalized["canonical_tcgplayer_product_id"] = df[id_col].map(normalize_id) if id_col else pd.Series([None] * len(df))
    normalized["observation_date"] = parse_date_series(df[date_col]).dt.date.astype("string") if date_col else pd.Series([pd.NA] * len(df), dtype="string")
    normalized["market_price"] = pd.to_numeric(df[price_col], errors="coerce") if price_col else pd.Series([pd.NA] * len(df))
    normalized["product_name_source"] = df[name_col].astype("string") if name_col else pd.Series([pd.NA] * len(df), dtype="string")
    normalized["source_file"] = rel
    normalized["source_row_number"] = range(2, len(df) + 2)
    normalized["source_id_column"] = id_col or ""
    normalized["source_date_column"] = date_col or ""
    normalized["source_price_column"] = price_col or ""
    normalized["is_governed_collector"] = normalized["canonical_tcgplayer_product_id"].isin(governed_ids)
    collector = normalized[normalized["is_governed_collector"]].copy()
    valid_dates = pd.to_datetime(collector["observation_date"], errors="coerce")
    profile = {
        "path": rel,
        "exists": True,
        "readable": True,
        "error": "",
        "row_count": int(len(df)),
        "id_column": id_col or "",
        "date_column": date_col or "",
        "price_column": price_col or "",
        "collector_row_count": int(len(collector)),
        "collector_product_count": int(collector["canonical_tcgplayer_product_id"].nunique(dropna=True)),
        "valid_collector_date_count": int(valid_dates.notna().sum()),
        "earliest_collector_date": None if valid_dates.dropna().empty else valid_dates.min().date().isoformat(),
        "latest_collector_date": None if valid_dates.dropna().empty else valid_dates.max().date().isoformat(),
        "positive_price_count": int((collector["market_price"] > 0).fillna(False).sum()),
        "candidate_deep_history": bool(valid_dates.notna().any() and valid_dates.min().date().isoformat() < "2026-07-01"),
    }
    return collector, profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = load_json(CONFIG)
    failures: list[str] = []
    release_map, inventory_rows = build_release_map(cfg)
    governed_ids = set(release_map["canonical_tcgplayer_product_id"].dropna())
    histories: list[pd.DataFrame] = []
    profiles: list[dict] = []
    for rel in cfg["candidate_history_sources"]:
        history, profile = profile_and_normalize_history(ROOT / rel, rel, governed_ids)
        profiles.append(profile)
        inventory_rows.append({"path": rel, "role": "HISTORY", "exists": profile.get("exists"), "readable": profile.get("readable"), "error": profile.get("error", "")})
        if not history.empty:
            histories.append(history)

    out_dir = ROOT / cfg["candidate_output_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(inventory_rows).to_csv(out_dir / "collector_deep_history_source_inventory.csv", index=False)
    release_map.to_csv(out_dir / "collector_release_identity_resolution.csv", index=False)
    pd.DataFrame(profiles).to_csv(out_dir / "collector_deep_history_source_profiles.csv", index=False)

    if histories:
        combined = pd.concat(histories, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=["canonical_tcgplayer_product_id", "observation_date", "market_price", "source_file"])
    combined = combined.merge(release_map, on="canonical_tcgplayer_product_id", how="left")
    combined["observation_date_parsed"] = pd.to_datetime(combined["observation_date"], errors="coerce")
    combined["release_date_parsed"] = pd.to_datetime(combined["release_date"], errors="coerce")
    combined["valid_observation"] = combined["observation_date_parsed"].notna() & combined["market_price"].gt(0)
    combined["post_release_or_unknown"] = combined["release_date_parsed"].isna() | (combined["observation_date_parsed"] >= combined["release_date_parsed"])
    combined["deep_history_candidate"] = combined["valid_observation"] & combined["post_release_or_unknown"] & (combined["observation_date_parsed"] < pd.Timestamp("2026-07-01"))
    combined["knowledge_availability_status"] = "RETROSPECTIVE_AVAILABILITY_UNPROVEN"
    combined["historical_decision_input_eligible"] = False
    combined["outcome_measurement_eligible"] = combined["valid_observation"] & combined["post_release_or_unknown"]
    combined["dedup_key"] = (
        combined["canonical_tcgplayer_product_id"].fillna("") + "|" +
        combined["observation_date"].fillna("") + "|" +
        combined["market_price"].round(6).astype("string").fillna("")
    )
    combined = combined.sort_values(["canonical_tcgplayer_product_id", "observation_date_parsed", "source_file"])
    exclusions = combined[~combined["outcome_measurement_eligible"]].copy()
    governed = combined[combined["outcome_measurement_eligible"]].drop_duplicates("dedup_key", keep="first").copy()
    governed.to_csv(out_dir / "collector_deep_history_candidate.csv", index=False)
    exclusions.to_csv(out_dir / "collector_deep_history_exclusions.csv", index=False)

    coverage = release_map.copy()
    grouped = governed.groupby("canonical_tcgplayer_product_id") if not governed.empty else None
    coverage["total_observation_count"] = coverage["canonical_tcgplayer_product_id"].map(grouped.size() if grouped is not None else {})
    coverage["deep_history_observation_count"] = coverage["canonical_tcgplayer_product_id"].map(grouped["deep_history_candidate"].sum() if grouped is not None else {})
    coverage["earliest_observation_date"] = coverage["canonical_tcgplayer_product_id"].map(grouped["observation_date_parsed"].min().dt.date.astype("string") if grouped is not None else {})
    coverage["latest_observation_date"] = coverage["canonical_tcgplayer_product_id"].map(grouped["observation_date_parsed"].max().dt.date.astype("string") if grouped is not None else {})
    coverage[["total_observation_count", "deep_history_observation_count"]] = coverage[["total_observation_count", "deep_history_observation_count"]].fillna(0).astype(int)
    coverage["has_deep_history_candidate"] = coverage["deep_history_observation_count"] > 0
    coverage["historical_decision_input_ready"] = False
    coverage.to_csv(out_dir / "collector_decision_date_coverage.csv", index=False)

    source_profile_df = pd.DataFrame(profiles)
    summary = {
        "audit_name": "Collector Deep History Recovery Candidate",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "governed_product_count": int(len(release_map)),
        "product_with_name_count": int(release_map["product_name"].fillna("").str.strip().ne("").sum()),
        "product_with_release_date_count": int(release_map["release_date"].fillna("").str.strip().ne("").sum()),
        "history_source_count": len(cfg["candidate_history_sources"]),
        "history_source_present_count": int(source_profile_df.get("exists", pd.Series(dtype=bool)).fillna(False).sum()),
        "deep_history_source_count": int(source_profile_df.get("candidate_deep_history", pd.Series(dtype=bool)).fillna(False).sum()),
        "governed_outcome_observation_count": int(len(governed)),
        "deep_history_observation_count": int(governed["deep_history_candidate"].sum()) if not governed.empty else 0,
        "products_with_deep_history_count": int(coverage["has_deep_history_candidate"].sum()),
        "historical_decision_input_eligible_count": 0,
        "historical_snapshot_builder_authorized": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "governing_note": "This batch recovers and profiles locally available deep history, release metadata, and product coverage. It does not prove historical knowledge availability or authorize snapshots, forecasts, or purchases.",
    }
    (out_dir / "collector_deep_history_recovery_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
