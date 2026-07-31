from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_historical_ledger_semantic_review_candidate_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def truthy(value: object) -> bool:
    return bool(value)


def summarize_ledger(path: Path, registry_ids: set[str]) -> dict:
    df = pd.read_csv(path, low_memory=False)
    for column in ("tcgplayer_product_id", "canonical_product_id", "observation_fingerprint"):
        if column in df.columns:
            df[column] = df[column].astype("string")

    if "tcgplayer_product_id" in df.columns:
        ids = set(df["tcgplayer_product_id"].dropna().str.strip())
    else:
        ids = set()

    collector_rows = df[df.get("tcgplayer_product_id", pd.Series(dtype="string")).isin(registry_ids)].copy()
    observation_dates = pd.to_datetime(collector_rows.get("observation_date"), errors="coerce", utc=True)
    observed_times = pd.to_datetime(collector_rows.get("observed_at_utc"), errors="coerce", utc=True)
    market_prices = pd.to_numeric(collector_rows.get("market_price"), errors="coerce")

    fingerprints = collector_rows.get("observation_fingerprint", pd.Series(dtype="string"))
    duplicate_fingerprint_rows = int(fingerprints.duplicated(keep=False).sum()) if len(fingerprints) else 0

    live_values = collector_rows.get("is_live_observation", pd.Series(dtype="object"))
    live_normalized = live_values.astype("string").str.lower().str.strip()

    result = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "row_count": int(len(df)),
        "distinct_product_id_count": int(len(ids)),
        "collector_row_count": int(len(collector_rows)),
        "collector_product_count": int(collector_rows.get("tcgplayer_product_id", pd.Series(dtype="string")).nunique(dropna=True)),
        "collector_registry_coverage_count": int(len(ids & registry_ids)),
        "collector_registry_missing_count": int(len(registry_ids - ids)),
        "invalid_observation_date_count": int(observation_dates.isna().sum()),
        "invalid_observed_at_utc_count": int(observed_times.isna().sum()),
        "nonpositive_market_price_count": int((market_prices <= 0).fillna(False).sum()),
        "missing_market_price_count": int(market_prices.isna().sum()),
        "duplicate_fingerprint_row_count": duplicate_fingerprint_rows,
        "live_observation_row_count": int(live_normalized.isin(["true", "1", "yes"]).sum()),
        "nonlive_observation_row_count": int(live_normalized.isin(["false", "0", "no"]).sum()),
        "unknown_live_status_row_count": int((~live_normalized.isin(["true", "1", "yes", "false", "0", "no"])).sum()),
        "earliest_collector_observation_date": None if observation_dates.dropna().empty else observation_dates.min().date().isoformat(),
        "latest_collector_observation_date": None if observation_dates.dropna().empty else observation_dates.max().date().isoformat(),
        "source_name_count": int(collector_rows.get("source_name", pd.Series(dtype="string")).nunique(dropna=True)),
        "price_field_count": int(collector_rows.get("price_field", pd.Series(dtype="string")).nunique(dropna=True)),
        "currency_count": int(collector_rows.get("currency", pd.Series(dtype="string")).nunique(dropna=True)),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    cfg = load_json(CONFIG)

    required_top = [
        "primary_ledger",
        "supporting_ledger",
        "governed_registry",
        "required_reviews",
        "knowledge_availability_policy",
        "candidate_output_directory",
        "authorizations",
    ]
    for key in required_top:
        if key not in cfg:
            failures.append(f"missing_config_key:{key}")

    required_reviews = cfg.get("required_reviews", {})
    for key, value in required_reviews.items():
        if not truthy(value):
            failures.append(f"required_review_not_enabled:{key}")

    policy = cfg.get("knowledge_availability_policy", {})
    for key in [
        "observation_date_is_not_automatically_knowledge_available_date",
        "retrospective_backfills_must_be_visible",
        "retrospective_backfills_may_be_used_for_outcome_measurement",
        "retrospective_backfills_may_not_be_used_as_historical_decision_inputs_without_owner_approved_policy",
        "future_information_prohibited",
    ]:
        if not truthy(policy.get(key)):
            failures.append(f"knowledge_policy_missing:{key}")

    auth = cfg.get("authorizations", {})
    for key, value in auth.items():
        if truthy(value):
            failures.append(f"authorization_must_remain_false:{key}")

    primary = ROOT / cfg.get("primary_ledger", "")
    supporting = ROOT / cfg.get("supporting_ledger", "")
    registry = ROOT / cfg.get("governed_registry", "")

    for label, path in [("primary", primary), ("supporting", supporting), ("registry", registry)]:
        if not path.exists():
            failures.append(f"missing_{label}_path:{path}")

    outputs: dict[str, object] = {}
    if not failures:
        registry_df = pd.read_csv(registry, low_memory=False)
        if "tcgplayer_product_id" not in registry_df.columns:
            failures.append("registry_missing_tcgplayer_product_id")
        else:
            registry_ids = set(registry_df["tcgplayer_product_id"].astype("string").dropna().str.strip())
            primary_summary = summarize_ledger(primary, registry_ids)
            supporting_summary = summarize_ledger(supporting, registry_ids)

            primary_df = pd.read_csv(primary, low_memory=False)
            supporting_df = pd.read_csv(supporting, low_memory=False)
            key_cols = [
                col
                for col in ["observation_fingerprint"]
                if col in primary_df.columns and col in supporting_df.columns
            ]
            overlap_count = 0
            if key_cols:
                primary_keys = set(primary_df[key_cols[0]].astype("string").dropna())
                supporting_keys = set(supporting_df[key_cols[0]].astype("string").dropna())
                overlap_count = len(primary_keys & supporting_keys)

            outputs = {
                "registry_product_count": len(registry_ids),
                "primary": primary_summary,
                "supporting": supporting_summary,
                "primary_supporting_fingerprint_overlap_count": overlap_count,
            }

            out_dir = ROOT / cfg["candidate_output_directory"]
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "collector_historical_ledger_semantic_review_summary.json").write_text(
                json.dumps(outputs, indent=2, sort_keys=True), encoding="utf-8"
            )
            pd.DataFrame([primary_summary, supporting_summary]).to_csv(
                out_dir / "collector_historical_ledger_source_summary.csv", index=False
            )

    status = "PASS" if not failures else "FAIL"
    summary = {
        "audit_name": "Collector Historical Ledger Semantic Review Candidate Audit",
        "audit_version": "1.0.0",
        "status": status,
        "failure_count": len(failures),
        "failures": failures,
        "primary_ledger_authorized": bool(auth.get("primary_ledger_authorized", False)),
        "historical_snapshot_builder_authorized": bool(auth.get("historical_snapshot_builder_authorized", False)),
        "projection_authorized": bool(auth.get("projection_authorized", False)),
        "purchase_recommendation_authorized": bool(auth.get("purchase_recommendation_authorized", False)),
        "future_information_prohibited": bool(policy.get("future_information_prohibited", False)),
        "governing_note": "This audit profiles Collector ledger semantics and coverage only. It does not authorize the ledger, construct historical snapshots, or run forecasts.",
        **outputs,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
