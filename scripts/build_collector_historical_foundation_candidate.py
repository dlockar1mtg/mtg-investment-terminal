from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_historical_foundation_candidate_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_id(value: object) -> str | None:
    """Normalize CSV identifiers such as 123456, 123456.0, and ' 123456 '."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "<na>"}:
        return None
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        text = text.split(".", 1)[0]
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    try:
        numeric = float(text)
        if math.isfinite(numeric) and numeric.is_integer():
            return str(int(numeric))
    except ValueError:
        pass
    return None


def normalize_bool(value: object) -> bool | None:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((column for column in candidates if column in df.columns), None)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def build_universe(cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    inputs = cfg["inputs"]
    registry_path = ROOT / inputs["governed_registry"]
    registry = read_csv(registry_path)
    failures: list[str] = []

    id_column = first_existing_column(registry, ["tcgplayer_product_id", "approved_tcgplayer_product_id"])
    if id_column is None:
        raise ValueError("governed registry lacks a TCGplayer product ID column")

    registry["raw_tcgplayer_product_id"] = registry[id_column].astype("string")
    registry["canonical_tcgplayer_product_id"] = registry[id_column].map(canonical_id)
    registry["universe_source"] = "GOVERNED_REGISTRY"

    admissions_path = ROOT / inputs.get("applied_admissions", "")
    frames = [registry]
    if admissions_path.exists():
        admissions = read_csv(admissions_path)
        admission_id = first_existing_column(admissions, ["tcgplayer_product_id", "approved_tcgplayer_product_id"])
        if admission_id:
            admissions["raw_tcgplayer_product_id"] = admissions[admission_id].astype("string")
            admissions["canonical_tcgplayer_product_id"] = admissions[admission_id].map(canonical_id)
            admissions["universe_source"] = "APPLIED_ADMISSION"
            frames.append(admissions)

    combined_columns = sorted(set().union(*(set(frame.columns) for frame in frames)))
    aligned = [frame.reindex(columns=combined_columns) for frame in frames]
    universe = pd.concat(aligned, ignore_index=True)

    name_column = first_existing_column(
        universe,
        ["canonical_product_name", "approved_product_name", "product_name", "box_name", "official_product_name"],
    )
    release_column = first_existing_column(universe, ["release_date", "governed_release_date", "published_on"])
    canonical_column = first_existing_column(universe, ["canonical_product_id", "investment_product_id"])

    universe["product_name"] = universe[name_column].astype("string") if name_column else pd.Series(pd.NA, index=universe.index, dtype="string")
    universe["release_date"] = pd.to_datetime(universe[release_column], errors="coerce").dt.date.astype("string") if release_column else pd.Series(pd.NA, index=universe.index, dtype="string")
    universe["canonical_product_id_output"] = universe[canonical_column].astype("string") if canonical_column else pd.Series(pd.NA, index=universe.index, dtype="string")

    missing_ids = universe["canonical_tcgplayer_product_id"].isna()
    if missing_ids.any():
        failures.append(f"universe_rows_with_invalid_id:{int(missing_ids.sum())}")

    conflicts = (
        universe.dropna(subset=["canonical_tcgplayer_product_id"])
        .groupby("canonical_tcgplayer_product_id")["product_name"]
        .nunique(dropna=True)
    )
    conflict_ids = set(conflicts[conflicts > 1].index.astype(str))
    if conflict_ids:
        failures.append(f"identity_name_conflicts:{len(conflict_ids)}")

    universe = universe.sort_values(["canonical_tcgplayer_product_id", "universe_source"]).drop_duplicates(
        subset=["canonical_tcgplayer_product_id"], keep="first"
    )
    return universe, failures


def profile_ledger(label: str, path: Path, universe_ids: set[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = read_csv(path)
    id_column = first_existing_column(df, ["tcgplayer_product_id", "source_product_id", "canonical_product_id"])
    if id_column is None:
        raise ValueError(f"{label} ledger lacks a usable product ID column")

    df["raw_tcgplayer_product_id"] = df[id_column].astype("string")
    df["canonical_tcgplayer_product_id"] = df[id_column].map(canonical_id)
    df["ledger_source"] = label
    df["observation_date_parsed"] = pd.to_datetime(df.get("observation_date"), errors="coerce", utc=True)
    df["observed_at_utc_parsed"] = pd.to_datetime(df.get("observed_at_utc"), errors="coerce", utc=True)
    df["market_price_numeric"] = pd.to_numeric(df.get("market_price"), errors="coerce")
    df["is_live_normalized"] = df.get("is_live_observation", pd.Series(pd.NA, index=df.index)).map(normalize_bool)

    collector = df[df["canonical_tcgplayer_product_id"].isin(universe_ids)].copy()
    ids = set(df["canonical_tcgplayer_product_id"].dropna().astype(str))
    collector_ids = set(collector["canonical_tcgplayer_product_id"].dropna().astype(str))

    summary = {
        "ledger_source": label,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "row_count": int(len(df)),
        "distinct_normalized_product_count": int(df["canonical_tcgplayer_product_id"].nunique(dropna=True)),
        "invalid_identifier_row_count": int(df["canonical_tcgplayer_product_id"].isna().sum()),
        "collector_row_count": int(len(collector)),
        "collector_product_count": int(len(collector_ids)),
        "collector_coverage_count": int(len(collector_ids & universe_ids)),
        "collector_missing_count": int(len(universe_ids - collector_ids)),
        "invalid_observation_date_count": int(collector["observation_date_parsed"].isna().sum()),
        "invalid_observed_at_utc_count": int(collector["observed_at_utc_parsed"].isna().sum()),
        "missing_market_price_count": int(collector["market_price_numeric"].isna().sum()),
        "nonpositive_market_price_count": int((collector["market_price_numeric"] <= 0).fillna(False).sum()),
        "live_observation_row_count": int((collector["is_live_normalized"] == True).sum()),  # noqa: E712
        "nonlive_observation_row_count": int((collector["is_live_normalized"] == False).sum()),  # noqa: E712
        "unknown_live_status_row_count": int(collector["is_live_normalized"].isna().sum()),
        "source_name_count": int(collector.get("source_name", pd.Series(dtype="string")).nunique(dropna=True)),
        "price_field_count": int(collector.get("price_field", pd.Series(dtype="string")).nunique(dropna=True)),
        "currency_count": int(collector.get("currency", pd.Series(dtype="string")).nunique(dropna=True)),
        "earliest_observation_date": None if collector["observation_date_parsed"].dropna().empty else collector["observation_date_parsed"].min().date().isoformat(),
        "latest_observation_date": None if collector["observation_date_parsed"].dropna().empty else collector["observation_date_parsed"].max().date().isoformat(),
    }
    return collector, summary


def make_dedup_key(df: pd.DataFrame) -> pd.Series:
    fingerprints = df.get("observation_fingerprint", pd.Series(pd.NA, index=df.index, dtype="string")).astype("string").str.strip()
    fallback = (
        df["canonical_tcgplayer_product_id"].astype("string").fillna("")
        + "|"
        + df["observation_date_parsed"].astype("string").fillna("")
        + "|"
        + df.get("source_name", pd.Series("", index=df.index)).astype("string").fillna("")
        + "|"
        + df.get("price_field", pd.Series("", index=df.index)).astype("string").fillna("")
        + "|"
        + df["market_price_numeric"].astype("string").fillna("")
    )
    return fingerprints.where(fingerprints.notna() & fingerprints.ne(""), fallback)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_json(CONFIG)
    failures: list[str] = []
    warnings: list[str] = []

    for key, value in cfg.get("authorizations", {}).items():
        if bool(value):
            failures.append(f"authorization_must_remain_false:{key}")

    try:
        universe, universe_failures = build_universe(cfg)
        failures.extend(universe_failures)
    except Exception as exc:  # pragma: no cover - fail-safe reporting
        failures.append(f"universe_build_failed:{type(exc).__name__}:{exc}")
        universe = pd.DataFrame()

    out_dir = ROOT / cfg["output_directory"]
    out_dir.mkdir(parents=True, exist_ok=True)

    if not universe.empty:
        universe_ids = set(universe["canonical_tcgplayer_product_id"].dropna().astype(str))
        primary_path = ROOT / cfg["inputs"]["primary_ledger"]
        supporting_path = ROOT / cfg["inputs"]["supporting_ledger"]

        try:
            primary, primary_summary = profile_ledger("PRIMARY", primary_path, universe_ids)
            supporting, supporting_summary = profile_ledger("SUPPORTING", supporting_path, universe_ids)
        except Exception as exc:  # pragma: no cover
            failures.append(f"ledger_profile_failed:{type(exc).__name__}:{exc}")
            primary = pd.DataFrame()
            supporting = pd.DataFrame()
            primary_summary = {}
            supporting_summary = {}

        if not primary.empty or not supporting.empty:
            primary["dedup_key"] = make_dedup_key(primary)
            supporting["dedup_key"] = make_dedup_key(supporting)
            primary_keys = set(primary["dedup_key"].dropna().astype(str))
            supporting_keys = set(supporting["dedup_key"].dropna().astype(str))
            overlap_keys = primary_keys & supporting_keys

            supporting_unique = supporting[~supporting["dedup_key"].isin(primary_keys)].copy()
            combined = pd.concat([primary, supporting_unique], ignore_index=True, sort=False)
            combined["source_precedence"] = combined["ledger_source"].map({"PRIMARY": 1, "SUPPORTING": 2}).fillna(9)
            combined = combined.sort_values(["dedup_key", "source_precedence"]).drop_duplicates("dedup_key", keep="first")

            registry_columns = [
                "canonical_tcgplayer_product_id",
                "canonical_product_id_output",
                "product_name",
                "release_date",
                "universe_source",
            ]
            governed = combined.merge(universe[registry_columns], on="canonical_tcgplayer_product_id", how="left", validate="many_to_one")
            governed["release_date_parsed"] = pd.to_datetime(governed["release_date"], errors="coerce", utc=True)
            governed["pre_release_observation"] = (
                governed["observation_date_parsed"].notna()
                & governed["release_date_parsed"].notna()
                & (governed["observation_date_parsed"] < governed["release_date_parsed"])
            )
            governed["knowledge_available_timestamp"] = governed["observed_at_utc_parsed"]
            governed["retrospective_observation"] = (
                governed["observed_at_utc_parsed"].notna()
                & governed["observation_date_parsed"].notna()
                & (governed["observed_at_utc_parsed"].dt.date > governed["observation_date_parsed"].dt.date)
            )
            governed["knowledge_availability_class"] = "UNKNOWN_FAIL_CLOSED"
            governed.loc[governed["is_live_normalized"] == True, "knowledge_availability_class"] = "CONTEMPORANEOUS_LIVE"  # noqa: E712
            governed.loc[governed["is_live_normalized"] == False, "knowledge_availability_class"] = "RETROSPECTIVE_BACKFILL"  # noqa: E712
            governed.loc[
                governed["is_live_normalized"].isna() & governed["retrospective_observation"],
                "knowledge_availability_class",
            ] = "RETROSPECTIVE_BY_TIMESTAMP"
            governed.loc[
                governed["is_live_normalized"].isna()
                & ~governed["retrospective_observation"]
                & governed["observed_at_utc_parsed"].notna(),
                "knowledge_availability_class",
            ] = "TIMESTAMP_AVAILABLE_UNVERIFIED"

            governed["outcome_measurement_eligible"] = (
                governed["market_price_numeric"].notna()
                & (governed["market_price_numeric"] > 0)
                & governed["observation_date_parsed"].notna()
                & ~governed["pre_release_observation"]
            )
            governed["historical_decision_input_eligible"] = (
                governed["outcome_measurement_eligible"]
                & governed["knowledge_availability_class"].eq("CONTEMPORANEOUS_LIVE")
            )

            exclusion_reasons = pd.Series("", index=governed.index, dtype="string")
            exclusion_reasons = exclusion_reasons.mask(governed["canonical_tcgplayer_product_id"].isna(), "INVALID_PRODUCT_ID")
            exclusion_reasons = exclusion_reasons.mask(governed["observation_date_parsed"].isna(), "INVALID_OBSERVATION_DATE")
            exclusion_reasons = exclusion_reasons.mask(governed["market_price_numeric"].isna(), "MISSING_MARKET_PRICE")
            exclusion_reasons = exclusion_reasons.mask((governed["market_price_numeric"] <= 0).fillna(False), "NONPOSITIVE_MARKET_PRICE")
            exclusion_reasons = exclusion_reasons.mask(governed["pre_release_observation"], "PRE_RELEASE_OBSERVATION")
            exclusion_reasons = exclusion_reasons.mask(
                ~governed["historical_decision_input_eligible"] & exclusion_reasons.eq(""),
                "NOT_PROVEN_HISTORICALLY_AVAILABLE",
            )
            governed["decision_input_exclusion_reason"] = exclusion_reasons

            output_columns = [
                "canonical_product_id_output",
                "canonical_tcgplayer_product_id",
                "product_name",
                "release_date",
                "ledger_source",
                "observation_date",
                "observed_at_utc",
                "knowledge_available_timestamp",
                "knowledge_availability_class",
                "market_price_numeric",
                "low_price",
                "high_price",
                "listing_count",
                "seller_count",
                "currency",
                "price_field",
                "source_name",
                "source_product_id",
                "mapping_method",
                "source_file",
                "collection_run_id",
                "is_live_observation",
                "observation_fingerprint",
                "dedup_key",
                "pre_release_observation",
                "retrospective_observation",
                "historical_decision_input_eligible",
                "outcome_measurement_eligible",
                "decision_input_exclusion_reason",
            ]
            for column in output_columns:
                if column not in governed.columns:
                    governed[column] = pd.NA

            governed[output_columns].to_csv(out_dir / "collector_governed_historical_observations.csv", index=False)
            governed.loc[~governed["historical_decision_input_eligible"], output_columns].to_csv(
                out_dir / "collector_historical_exclusions.csv", index=False
            )

            product_readiness = (
                governed.groupby(["canonical_tcgplayer_product_id", "product_name", "release_date"], dropna=False)
                .agg(
                    total_observation_count=("dedup_key", "count"),
                    decision_input_eligible_count=("historical_decision_input_eligible", "sum"),
                    outcome_eligible_count=("outcome_measurement_eligible", "sum"),
                    earliest_observation_date=("observation_date_parsed", "min"),
                    latest_observation_date=("observation_date_parsed", "max"),
                    source_count=("source_name", "nunique"),
                    price_field_count=("price_field", "nunique"),
                    retrospective_count=("retrospective_observation", "sum"),
                    pre_release_count=("pre_release_observation", "sum"),
                )
                .reset_index()
            )
            product_readiness["snapshot_input_availability"] = product_readiness["decision_input_eligible_count"].map(
                lambda count: "HAS_PROVEN_HISTORICAL_INPUTS" if count > 0 else "NO_PROVEN_HISTORICAL_INPUTS"
            )
            product_readiness["outcome_availability"] = product_readiness["outcome_eligible_count"].map(
                lambda count: "HAS_OUTCOME_HISTORY" if count > 0 else "NO_OUTCOME_HISTORY"
            )
            product_readiness.to_csv(out_dir / "collector_product_history_readiness.csv", index=False)

            universe_reconciliation = universe[
                ["canonical_product_id_output", "canonical_tcgplayer_product_id", "product_name", "release_date", "universe_source"]
            ].copy()
            coverage = set(governed["canonical_tcgplayer_product_id"].dropna().astype(str))
            input_coverage = set(
                governed.loc[governed["historical_decision_input_eligible"], "canonical_tcgplayer_product_id"].dropna().astype(str)
            )
            universe_reconciliation["history_present"] = universe_reconciliation["canonical_tcgplayer_product_id"].isin(coverage)
            universe_reconciliation["proven_historical_decision_input_present"] = universe_reconciliation[
                "canonical_tcgplayer_product_id"
            ].isin(input_coverage)
            universe_reconciliation.to_csv(out_dir / "collector_identity_reconciliation.csv", index=False)

            pd.DataFrame([primary_summary, supporting_summary]).to_csv(out_dir / "collector_ledger_source_profile.csv", index=False)
            overlap_summary = {
                "primary_key_count": len(primary_keys),
                "supporting_key_count": len(supporting_keys),
                "overlap_key_count": len(overlap_keys),
                "primary_unique_key_count": len(primary_keys - supporting_keys),
                "supporting_unique_key_count": len(supporting_keys - primary_keys),
                "relationship_classification": (
                    "SUPPORTING_IS_SUBSET_OF_PRIMARY"
                    if supporting_keys and supporting_keys <= primary_keys
                    else "PARTIAL_OVERLAP_REQUIRES_UNION"
                    if overlap_keys
                    else "DISJOINT_SOURCES"
                ),
            }
            (out_dir / "collector_ledger_overlap_summary.json").write_text(
                json.dumps(overlap_summary, indent=2, sort_keys=True), encoding="utf-8"
            )

            summary = {
                "audit_name": "Collector Historical Foundation Candidate",
                "audit_version": "1.0.0",
                "status": "PASS" if not failures else "FAIL",
                "failure_count": len(failures),
                "failures": failures,
                "warnings": warnings,
                "governed_universe_product_count": len(universe_ids),
                "products_with_any_history_count": len(coverage),
                "products_with_proven_historical_decision_inputs_count": len(input_coverage),
                "governed_observation_count": int(len(governed)),
                "decision_input_eligible_observation_count": int(governed["historical_decision_input_eligible"].sum()),
                "outcome_eligible_observation_count": int(governed["outcome_measurement_eligible"].sum()),
                "retrospective_observation_count": int(governed["retrospective_observation"].sum()),
                "pre_release_observation_count": int(governed["pre_release_observation"].sum()),
                "primary": primary_summary,
                "supporting": supporting_summary,
                "overlap": overlap_summary,
                "historical_foundation_authorized": False,
                "historical_snapshot_builder_authorized": False,
                "projection_authorized": False,
                "purchase_recommendation_authorized": False,
                "governing_note": "This candidate fixes identity normalization and constructs a governed diagnostic history foundation. It does not approve sources, authorize historical snapshots, activate forecasts, or authorize purchases.",
            }
            (out_dir / "collector_historical_foundation_summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
            )
            print(json.dumps(summary, indent=2, sort_keys=True, default=str))
        else:
            failures.append("no_collector_rows_after_normalized_join")
    else:
        failures.append("empty_governed_universe")

    if failures and (out_dir / "collector_historical_foundation_summary.json").exists() is False:
        summary = {
            "audit_name": "Collector Historical Foundation Candidate",
            "audit_version": "1.0.0",
            "status": "FAIL",
            "failure_count": len(failures),
            "failures": failures,
            "historical_foundation_authorized": False,
            "historical_snapshot_builder_authorized": False,
            "projection_authorized": False,
            "purchase_recommendation_authorized": False,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
