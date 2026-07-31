from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_dual_track_evaluation_candidate_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_id(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "<na>"}:
        return None
    match = re.fullmatch(r"([0-9]+)(?:\.0+)?", text)
    return match.group(1) if match else None


def first_existing(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def first_nonblank(values: Iterable[object]) -> str | None:
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "null", "<na>"}:
            return text
    return None


def truthy_series(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.lower().isin({"true", "1", "yes", "y"})


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def collector_like_mask(df: pd.DataFrame) -> pd.Series:
    columns = [
        c
        for c in [
            "product_name",
            "canonical_product_name",
            "box_name",
            "approved_product_name",
            "official_product_name",
            "investment_product_type",
            "product_class",
            "lane",
        ]
        if c in df.columns
    ]
    if not columns:
        return pd.Series(False, index=df.index)
    combined = pd.Series("", index=df.index, dtype="string")
    for column in columns:
        combined = combined.str.cat(df[column].astype("string").fillna(""), sep=" ")
    lowered = combined.str.lower()
    return lowered.str.contains("collector", na=False) & ~lowered.str.contains("secret lair", na=False)


def build_universe(cfg: dict, failures: list[str]) -> pd.DataFrame:
    inputs = cfg["inputs"]
    registry_path = ROOT / inputs["governed_registry"]
    admissions_path = ROOT / inputs["applied_admissions"]
    master_path = ROOT / inputs["product_master"]
    release_path = ROOT / inputs["release_resolution"]

    for label, path in [
        ("registry", registry_path),
        ("admissions", admissions_path),
        ("product_master", master_path),
        ("release_resolution", release_path),
    ]:
        if not path.exists():
            failures.append(f"missing_{label}:{path}")

    if failures:
        return pd.DataFrame()

    registry = read_csv(registry_path)
    admissions = read_csv(admissions_path)
    master = read_csv(master_path)
    release = read_csv(release_path)

    sources: list[pd.DataFrame] = []

    def project(df: pd.DataFrame, source: str, force_collector: bool = False) -> pd.DataFrame:
        id_col = first_existing(df, ["tcgplayer_product_id", "approved_tcgplayer_product_id", "canonical_tcgplayer_product_id"])
        if id_col is None:
            return pd.DataFrame()
        work = df.copy()
        if not force_collector:
            work = work[collector_like_mask(work)].copy()
        work["canonical_tcgplayer_product_id"] = work[id_col].map(normalize_id)
        work = work[work["canonical_tcgplayer_product_id"].notna()].copy()
        name_col = first_existing(work, ["canonical_product_name", "product_name", "approved_product_name", "official_product_name", "box_name"])
        release_col = first_existing(work, ["release_date", "published_on", "governed_release_date", "final_release_date_assigned"])
        canonical_col = first_existing(work, ["canonical_product_id", "investment_product_id"])
        projected = pd.DataFrame({
            "canonical_tcgplayer_product_id": work["canonical_tcgplayer_product_id"],
            "product_name_candidate": work[name_col] if name_col else None,
            "release_date_candidate": work[release_col] if release_col else None,
            "canonical_product_id_candidate": work[canonical_col] if canonical_col else None,
            "universe_source": source,
        })
        return projected

    sources.append(project(registry, "GOVERNED_REGISTRY", force_collector=True))
    sources.append(project(admissions, "APPLIED_ADMISSION"))
    sources.append(project(master, "PRODUCT_MASTER"))
    sources.append(project(release, "RELEASE_RESOLUTION"))

    combined = pd.concat([x for x in sources if not x.empty], ignore_index=True)
    if combined.empty:
        failures.append("collector_universe_empty")
        return combined

    source_priority = {
        "GOVERNED_REGISTRY": 1,
        "APPLIED_ADMISSION": 2,
        "PRODUCT_MASTER": 3,
        "RELEASE_RESOLUTION": 4,
    }
    combined["source_priority"] = combined["universe_source"].map(source_priority).fillna(99)
    combined = combined.sort_values(["canonical_tcgplayer_product_id", "source_priority"])

    rows: list[dict] = []
    now_date = datetime.now(timezone.utc).date()
    for product_id, group in combined.groupby("canonical_tcgplayer_product_id", sort=True):
        names = group["product_name_candidate"].tolist()
        releases = group["release_date_candidate"].tolist()
        canonicals = group["canonical_product_id_candidate"].tolist()
        product_name = first_nonblank(names)
        release_text = first_nonblank(releases)
        release_date = pd.to_datetime(release_text, errors="coerce")
        release_iso = None if pd.isna(release_date) else release_date.date().isoformat()
        canonical_product_id = first_nonblank(canonicals) or f"TCGPLAYER-{product_id}"
        source_list = "|".join(dict.fromkeys(group["universe_source"].astype(str).tolist()))
        unresolved = product_name is None or release_iso is None
        future_release = False if release_iso is None else pd.Timestamp(release_iso).date() > now_date
        rows.append({
            "canonical_product_id": canonical_product_id,
            "canonical_tcgplayer_product_id": product_id,
            "product_name": product_name,
            "release_date": release_iso,
            "universe_sources": source_list,
            "identity_resolved": not unresolved,
            "future_release": future_release,
            "current_investment_eligible": (not unresolved) and (not future_release),
        })

    universe = pd.DataFrame(rows)
    universe = universe.sort_values(["product_name", "canonical_tcgplayer_product_id"], na_position="last")
    return universe


def build_retrospective_history(cfg: dict, universe: pd.DataFrame, failures: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = ROOT / cfg["inputs"]["deep_history_candidate"]
    if not path.exists():
        failures.append(f"missing_deep_history_candidate:{path}")
        return pd.DataFrame(), pd.DataFrame()

    history = read_csv(path)
    id_col = first_existing(history, ["canonical_tcgplayer_product_id", "tcgplayer_product_id"])
    date_col = first_existing(history, ["observation_date", "date", "snapshot_date"])
    price_col = first_existing(history, ["market_price", "price", "observed_price"])
    if not id_col or not date_col or not price_col:
        failures.append("deep_history_missing_required_columns")
        return pd.DataFrame(), pd.DataFrame()

    history = history.copy()
    history["canonical_tcgplayer_product_id"] = history[id_col].map(normalize_id)
    universe_ids = set(universe["canonical_tcgplayer_product_id"].dropna().astype(str))
    history = history[history["canonical_tcgplayer_product_id"].isin(universe_ids)].copy()
    history["observation_date_parsed"] = pd.to_datetime(history[date_col], errors="coerce", utc=True)
    history["market_price_normalized"] = pd.to_numeric(history[price_col], errors="coerce")

    release_map = universe.set_index("canonical_tcgplayer_product_id")["release_date"].to_dict()
    name_map = universe.set_index("canonical_tcgplayer_product_id")["product_name"].to_dict()
    canonical_map = universe.set_index("canonical_tcgplayer_product_id")["canonical_product_id"].to_dict()
    history["release_date"] = history["canonical_tcgplayer_product_id"].map(release_map)
    history["release_date_parsed"] = pd.to_datetime(history["release_date"], errors="coerce", utc=True)
    history["product_name"] = history["canonical_tcgplayer_product_id"].map(name_map)
    history["canonical_product_id"] = history["canonical_tcgplayer_product_id"].map(canonical_map)

    history["valid_observation_date"] = history["observation_date_parsed"].notna()
    history["valid_positive_price"] = history["market_price_normalized"].gt(0)
    history["release_boundary_satisfied"] = (
        history["release_date_parsed"].notna()
        & history["observation_date_parsed"].notna()
        & (history["observation_date_parsed"] >= history["release_date_parsed"])
    )
    history["retrospective_outcome_eligible"] = (
        history["valid_observation_date"]
        & history["valid_positive_price"]
        & history["release_boundary_satisfied"]
    )
    history["historical_decision_input_eligible"] = False
    history["knowledge_availability_status"] = "RETROSPECTIVE_AVAILABILITY_UNPROVEN"
    history["observation_date"] = history["observation_date_parsed"].dt.date.astype("string")
    history["market_price"] = history["market_price_normalized"]

    source_col = first_existing(history, ["source_path", "source_file", "source_name"])
    if source_col:
        history["source_lineage"] = history[source_col].astype("string")
    else:
        history["source_lineage"] = "UNSPECIFIED_SOURCE"

    history["dedup_key"] = (
        history["canonical_tcgplayer_product_id"].astype("string")
        + "|" + history["observation_date"].astype("string")
        + "|" + history["market_price"].round(6).astype("string")
        + "|" + history["source_lineage"].astype("string")
    )
    history = history.sort_values(["canonical_tcgplayer_product_id", "observation_date", "source_lineage"])
    history = history.drop_duplicates("dedup_key", keep="first")

    output_cols = [
        "canonical_product_id",
        "canonical_tcgplayer_product_id",
        "product_name",
        "release_date",
        "observation_date",
        "market_price",
        "source_lineage",
        "knowledge_availability_status",
        "historical_decision_input_eligible",
        "retrospective_outcome_eligible",
        "valid_observation_date",
        "valid_positive_price",
        "release_boundary_satisfied",
        "dedup_key",
    ]
    outcome = history[output_cols].copy()

    coverage_rows: list[dict] = []
    for _, product in universe.iterrows():
        pid = str(product["canonical_tcgplayer_product_id"])
        group = outcome[outcome["canonical_tcgplayer_product_id"] == pid]
        eligible = group[group["retrospective_outcome_eligible"]]
        dates = pd.to_datetime(eligible["observation_date"], errors="coerce")
        coverage_rows.append({
            "canonical_product_id": product["canonical_product_id"],
            "canonical_tcgplayer_product_id": pid,
            "product_name": product["product_name"],
            "release_date": product["release_date"],
            "future_release": product["future_release"],
            "total_recovered_observation_count": int(len(group)),
            "retrospective_outcome_eligible_count": int(len(eligible)),
            "historical_decision_input_eligible_count": 0,
            "earliest_outcome_observation_date": None if dates.dropna().empty else dates.min().date().isoformat(),
            "latest_outcome_observation_date": None if dates.dropna().empty else dates.max().date().isoformat(),
            "retrospective_outcome_history_available": bool(len(eligible)),
            "historical_decision_history_available": False,
        })
    coverage = pd.DataFrame(coverage_rows)
    return outcome, coverage


def build_prospective_snapshot(cfg: dict, universe: pd.DataFrame, failures: list[str]) -> tuple[pd.DataFrame, dict]:
    inputs = cfg["inputs"]
    master_path = ROOT / inputs["product_master"]
    route_path = ROOT / inputs["current_route_reference"]
    numeric_path = ROOT / inputs["numeric_candidate"]

    for label, path in [("product_master", master_path), ("route_reference", route_path), ("numeric_candidate", numeric_path)]:
        if not path.exists():
            failures.append(f"missing_{label}:{path}")
    if failures:
        return pd.DataFrame(), {}

    master = read_csv(master_path)
    routes = read_csv(route_path)
    numeric = load_json(numeric_path)

    master_id_col = first_existing(master, ["tcgplayer_product_id", "approved_tcgplayer_product_id", "canonical_tcgplayer_product_id"])
    route_id_col = first_existing(routes, ["investment_product_id", "tcgplayer_product_id", "canonical_tcgplayer_product_id"])
    if not master_id_col:
        failures.append("product_master_missing_identity")
        return pd.DataFrame(), {}

    master = master.copy()
    master["canonical_tcgplayer_product_id"] = master[master_id_col].map(normalize_id)
    master = master[master["canonical_tcgplayer_product_id"].notna()].copy()
    if route_id_col:
        routes = routes.copy()
        routes["route_join_id"] = routes[route_id_col].astype("string").str.extract(r"([0-9]+)$", expand=False)
        route_col = first_existing(routes, ["forecast_method", "route", "method_route"])
        route_map = routes.set_index("route_join_id")[route_col].to_dict() if route_col else {}
    else:
        route_map = {}

    master = master.drop_duplicates("canonical_tcgplayer_product_id", keep="last")
    master = universe.merge(master, on="canonical_tcgplayer_product_id", how="left", suffixes=("", "_master"))

    current_price_col = first_existing(master, ["current_price", "market_price", "current_price_history", "current_price_db"])
    price_date_col = first_existing(master, ["last_price_checked", "latest_observation_date", "latest_snapshot_date"])
    snapshot_time = datetime.now(timezone.utc)
    snapshot_date = snapshot_time.date().isoformat()
    model_version = f"{numeric.get('specification_name', 'Collector Numeric Methodology Candidate')} {numeric.get('specification_version', 'unknown')}"

    snapshot = pd.DataFrame({
        "snapshot_id": [hashlib.sha256(f"{snapshot_date}|{pid}|{model_version}".encode("utf-8")).hexdigest()[:24] for pid in master["canonical_tcgplayer_product_id"]],
        "decision_date": snapshot_date,
        "captured_at_utc": snapshot_time.isoformat(),
        "canonical_product_id": master["canonical_product_id"],
        "canonical_tcgplayer_product_id": master["canonical_tcgplayer_product_id"],
        "product_name": master["product_name"],
        "release_date": master["release_date"],
        "future_release": master["future_release"],
        "current_investment_eligible": master["current_investment_eligible"],
        "current_price": pd.to_numeric(master[current_price_col], errors="coerce") if current_price_col else None,
        "current_price_date": master[price_date_col] if price_date_col else None,
        "forecast_method_route": master["canonical_product_id"].astype("string").str.extract(r"([0-9]+)$", expand=False).map(route_map),
        "candidate_model_version": model_version,
        "exact_numeric_specification_approved": bool(numeric.get("exact_numeric_specification_approved", False)),
        "projection_authorized": bool(numeric.get("projection_authorized", False)),
        "purchase_recommendation_authorized": bool(numeric.get("purchase_recommendation_authorized", False)),
    })

    evidence_fields = [
        "supply_score", "demand_score", "liquidity_score", "reprint_risk",
        "history_confidence", "data_quality_score", "volatility_score",
        "return_90d", "return_180d", "return_365d",
        "history_observations", "first_snapshot_date", "latest_snapshot_date",
    ]
    for field in evidence_fields:
        snapshot[field] = master[field] if field in master.columns else None

    snapshot["missing_current_price"] = snapshot["current_price"].isna() | snapshot["current_price"].le(0)
    snapshot["missing_route"] = snapshot["forecast_method_route"].isna() | snapshot["forecast_method_route"].astype("string").str.strip().eq("")
    snapshot["missing_release_date"] = snapshot["release_date"].isna() | snapshot["release_date"].astype("string").str.strip().eq("")
    snapshot["snapshot_complete_for_future_evaluation"] = ~snapshot[["missing_current_price", "missing_route", "missing_release_date"]].any(axis=1)
    snapshot["diagnostic_projection_status"] = "NOT_CALCULATED_IN_THIS_BATCH"
    snapshot["purchase_recommendation_status"] = "UNAUTHORIZED"

    manifest = {
        "snapshot_date": snapshot_date,
        "captured_at_utc": snapshot_time.isoformat(),
        "candidate_model_version": model_version,
        "product_count": int(len(snapshot)),
        "complete_snapshot_count": int(snapshot["snapshot_complete_for_future_evaluation"].sum()),
        "missing_current_price_count": int(snapshot["missing_current_price"].sum()),
        "missing_route_count": int(snapshot["missing_route"].sum()),
        "missing_release_date_count": int(snapshot["missing_release_date"].sum()),
        "append_safe_key": ["decision_date", "canonical_tcgplayer_product_id", "candidate_model_version"],
        "historical_decision_input_status": "PROSPECTIVE_CAPTURE_FROM_THIS_DATE_FORWARD",
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
    }
    return snapshot, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_json(CONFIG)
    failures: list[str] = []

    universe = build_universe(cfg, failures)
    history, coverage = build_retrospective_history(cfg, universe, failures) if not universe.empty else (pd.DataFrame(), pd.DataFrame())
    snapshot, manifest = build_prospective_snapshot(cfg, universe, failures) if not universe.empty else (pd.DataFrame(), {})

    out_dir = ROOT / cfg["outputs"]["directory"]
    out_dir.mkdir(parents=True, exist_ok=True)

    if not universe.empty:
        universe.to_csv(out_dir / cfg["outputs"]["collector_authoritative_universe"], index=False)
    if not history.empty:
        history.to_csv(out_dir / cfg["outputs"]["collector_retrospective_outcome_history"], index=False)
    if not coverage.empty:
        coverage.to_csv(out_dir / cfg["outputs"]["collector_retrospective_coverage"], index=False)
    if not snapshot.empty:
        snapshot.to_csv(out_dir / cfg["outputs"]["collector_prospective_decision_snapshot"], index=False)
    if manifest:
        (out_dir / cfg["outputs"]["collector_prospective_snapshot_manifest"]).write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

    auth = cfg["authorizations"]
    summary = {
        "audit_name": "Collector Dual-Track Evaluation Candidate",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "collector_universe_product_count": int(len(universe)),
        "resolved_identity_count": int(universe["identity_resolved"].sum()) if not universe.empty else 0,
        "future_release_product_count": int(universe["future_release"].sum()) if not universe.empty else 0,
        "current_investment_eligible_product_count": int(universe["current_investment_eligible"].sum()) if not universe.empty else 0,
        "retrospective_observation_count": int(len(history)),
        "retrospective_outcome_eligible_count": int(history["retrospective_outcome_eligible"].sum()) if not history.empty else 0,
        "historical_decision_input_eligible_count": int(history["historical_decision_input_eligible"].sum()) if not history.empty else 0,
        "prospective_snapshot_product_count": int(len(snapshot)),
        "prospective_snapshot_complete_count": int(snapshot["snapshot_complete_for_future_evaluation"].sum()) if not snapshot.empty else 0,
        "retrospective_history_authorized_as_historical_decision_input": bool(auth["retrospective_history_authorized_as_historical_decision_input"]),
        "historical_snapshot_builder_authorized": bool(auth["historical_snapshot_builder_authorized"]),
        "candidate_projection_authorized": bool(auth["candidate_projection_authorized"]),
        "production_projection_authorized": bool(auth["production_projection_authorized"]),
        "purchase_recommendation_authorized": bool(auth["purchase_recommendation_authorized"]),
        "automatic_model_update_allowed": bool(auth["automatic_model_update_allowed"]),
        "governing_note": "This candidate restores Collector-only scope and establishes separate retrospective outcome and prospective decision-snapshot tracks. It does not activate forecasts, purchases, or automatic model updates.",
    }
    (out_dir / cfg["outputs"]["collector_dual_track_summary"]).write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
