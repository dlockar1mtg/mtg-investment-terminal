from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_canonical_historical_price_contract_v1.json"
ADJUDICATION_BUILDER = ROOT / "scripts/build_precollector_historical_source_adjudication.py"
ADJUDICATION_DIR = ROOT / "artifacts/precollector/historical_source_adjudication"
FREEZE_DIR = ROOT / "artifacts/precollector/canonical_universe_freeze"
OUTPUT_DIR = ROOT / "artifacts/precollector/canonical_historical_prices"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_adjudication() -> None:
    completed = subprocess.run([sys.executable, str(ADJUDICATION_BUILDER)], cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"HISTORICAL_ADJUDICATION_REBUILD_FAILED: {completed.returncode}")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)
    run_adjudication()

    canonical_path = FREEZE_DIR / "precollector_canonical_product_universe_v1.csv"
    source_path = ADJUDICATION_DIR / "precollector_historical_source_adjudication_v1.csv"
    audit_path = ADJUDICATION_DIR / "precollector_historical_row_level_audit_v1.csv"
    required = [canonical_path, source_path, audit_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"CANONICAL_HISTORY_INPUT_MISSING: {missing}")
    if sha256_file(canonical_path) != contract["canonical_universe_sha256"]:
        raise RuntimeError("CANONICAL_UNIVERSE_HASH_DRIFT")

    canonical = pd.read_csv(canonical_path, dtype=str).fillna("")
    sources = pd.read_csv(source_path, dtype=str).fillna("")
    audit = pd.read_csv(audit_path, low_memory=False)
    if len(canonical) != int(contract["expected_product_count"]):
        raise RuntimeError(f"CANONICAL_COUNT_DRIFT: {len(canonical)}")
    admissible_sources = sources[sources["adjudication_status"].eq("SOURCE_ADMISSIBLE")]
    if len(admissible_sources) != int(contract["expected_admissible_source_count"]):
        raise RuntimeError(f"ADMISSIBLE_SOURCE_COUNT_DRIFT: {len(admissible_sources)}")

    work = audit[audit["row_admissible"].astype(str).str.casefold().eq("true")].copy()
    work = work[work["source_path"].isin(set(admissible_sources["relative_path"]))].copy()
    work["observation_timestamp"] = pd.to_datetime(work["observation_timestamp"], utc=True, errors="coerce")
    work["historical_price"] = pd.to_numeric(work["historical_price"], errors="coerce")
    work = work[work["observation_timestamp"].notna() & work["historical_price"].gt(0)].copy()
    if work.empty:
        raise RuntimeError("NO_ADMISSIBLE_HISTORICAL_ROWS")

    work["source_path"] = work["source_path"].astype(str)
    work = work.sort_values(["canonical_product_id", "observation_timestamp", "source_path"], kind="stable")
    duplicate_mask = work.duplicated(["canonical_product_id", "observation_timestamp"], keep=False)
    conflicts = work[duplicate_mask].copy()
    conflicts["price_conflict"] = conflicts.groupby(["canonical_product_id", "observation_timestamp"])["historical_price"].transform("nunique").gt(1)

    canonical_history = work.drop_duplicates(["canonical_product_id", "observation_timestamp"], keep="last").copy()
    canonical_history = canonical_history.rename(columns={"historical_price": "canonical_historical_price"})
    canonical_history["source_count_at_timestamp"] = work.groupby(["canonical_product_id", "observation_timestamp"])["source_path"].transform("nunique").reindex(canonical_history.index).fillna(1).astype(int)
    canonical_history["historical_authority_status"] = "CANONICAL_HISTORICAL_OBSERVATION"
    canonical_history["forecast_authorized"] = False
    canonical_history = canonical_history[[
        "canonical_product_id", "observation_timestamp", "canonical_historical_price",
        "source_path", "source_count_at_timestamp", "historical_authority_status", "forecast_authorized"
    ]].sort_values(["canonical_product_id", "observation_timestamp"], kind="stable")

    coverage = canonical_history.groupby("canonical_product_id", as_index=False).agg(
        historical_rows=("canonical_historical_price", "size"),
        distinct_observation_dates=("observation_timestamp", "nunique"),
        first_observation=("observation_timestamp", "min"),
        last_observation=("observation_timestamp", "max"),
        minimum_price=("canonical_historical_price", "min"),
        maximum_price=("canonical_historical_price", "max"),
    )
    coverage["history_depth_status"] = (
        coverage["historical_rows"].ge(int(contract["minimum_rows_per_product"]))
        & coverage["distinct_observation_dates"].ge(int(contract["minimum_distinct_dates_per_product"]))
    ).map({True: "HISTORY_DEPTH_ADMISSIBLE", False: "HISTORY_DEPTH_INSUFFICIENT"})

    missing_products = canonical[~canonical["canonical_product_id"].isin(set(coverage["canonical_product_id"]))].copy()
    missing_products["historical_blocking_reason"] = "NO_ADMISSIBLE_HISTORICAL_OBSERVATIONS"
    depth_admissible_products = int(coverage["history_depth_status"].eq("HISTORY_DEPTH_ADMISSIBLE").sum())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    history_output = OUTPUT_DIR / outputs["canonical_history_csv"]
    conflicts_output = OUTPUT_DIR / outputs["conflicts_csv"]
    coverage_output = OUTPUT_DIR / outputs["coverage_csv"]
    missing_output = OUTPUT_DIR / outputs["missing_products_csv"]
    canonical_history.to_csv(history_output, index=False)
    conflicts.to_csv(conflicts_output, index=False)
    coverage.to_csv(coverage_output, index=False)
    missing_products.to_csv(missing_output, index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_CANONICAL_HISTORICAL_PRICE_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_historical_rows": len(canonical_history),
        "historically_covered_products": int(coverage["canonical_product_id"].nunique()),
        "history_depth_admissible_products": depth_admissible_products,
        "products_without_history": len(missing_products),
        "duplicate_source_rows": len(conflicts),
        "duplicate_price_conflict_rows": int(conflicts["price_conflict"].sum()) if not conflicts.empty else 0,
        "historical_append_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    summary_output = OUTPUT_DIR / outputs["summary_json"]
    summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "canonical_universe_sha256": sha256_file(canonical_path),
        "source_adjudication_sha256": sha256_file(source_path),
        "row_level_audit_sha256": sha256_file(audit_path),
        "canonical_history_sha256": sha256_file(history_output),
        "conflicts_sha256": sha256_file(conflicts_output),
        "coverage_sha256": sha256_file(coverage_output),
        "missing_products_sha256": sha256_file(missing_output),
        "scope_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_CANONICAL_HISTORICAL_PRICE_BUILD")
    print(f"CANONICAL_HISTORICAL_ROWS={len(canonical_history)}")
    print(f"HISTORICALLY_COVERED_PRODUCTS={int(coverage['canonical_product_id'].nunique())}")
    print(f"HISTORY_DEPTH_ADMISSIBLE_PRODUCTS={depth_admissible_products}")
    print(f"PRODUCTS_WITHOUT_HISTORY={len(missing_products)}")
    print(f"DUPLICATE_SOURCE_ROWS={len(conflicts)}")
    print(f"DUPLICATE_PRICE_CONFLICT_ROWS={summary['duplicate_price_conflict_rows']}")
    print("NEXT_STAGE=PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
