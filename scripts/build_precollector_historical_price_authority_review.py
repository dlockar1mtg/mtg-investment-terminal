from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_historical_price_authority_review_contract_v1.json"
HISTORY_CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_canonical_historical_price_contract_v1.json"
CURRENT_CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_current_price_authority_review_contract_v1.json"
HISTORY_BUILDER = ROOT / "scripts/build_precollector_canonical_historical_prices.py"
CURRENT_REVIEW_BUILDER = ROOT / "scripts/build_precollector_current_price_authority_review.py"
FREEZE_DIR = ROOT / "artifacts/precollector/canonical_universe_freeze"
HISTORY_DIR = ROOT / "artifacts/precollector/canonical_historical_prices"
CURRENT_DIR = ROOT / "artifacts/precollector/current_price_authority_review"
OUTPUT_DIR = ROOT / "artifacts/precollector/historical_price_authority_review"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"SUBPROCESS_FAILED:{completed.returncode}:{' '.join(command)}")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    history_contract = load_json(HISTORY_CONTRACT_PATH)
    current_contract = load_json(CURRENT_CONTRACT_PATH)
    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)

    with tempfile.TemporaryDirectory(prefix="precollector_current_authority_") as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        run([sys.executable, str(CURRENT_REVIEW_BUILDER)])
        current_authorized_name = current_contract["outputs"]["authorized_csv"]
        current_blocked_name = current_contract["outputs"]["blocked_csv"]
        staged_authorized = temp_dir / current_authorized_name
        staged_blocked = temp_dir / current_blocked_name
        shutil.copy2(CURRENT_DIR / current_authorized_name, staged_authorized)
        shutil.copy2(CURRENT_DIR / current_blocked_name, staged_blocked)

        run([sys.executable, str(HISTORY_BUILDER)])
        CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged_authorized, CURRENT_DIR / current_authorized_name)
        shutil.copy2(staged_blocked, CURRENT_DIR / current_blocked_name)

    canonical_path = FREEZE_DIR / "precollector_canonical_product_universe_v1.csv"
    history_path = HISTORY_DIR / history_contract["outputs"]["canonical_history_csv"]
    current_authority_path = CURRENT_DIR / current_contract["outputs"]["authorized_csv"]
    current_blocked_path = CURRENT_DIR / current_contract["outputs"]["blocked_csv"]

    required_paths = [canonical_path, history_path, current_authority_path, current_blocked_path]
    missing = [str(path.relative_to(ROOT)) for path in required_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"HISTORICAL_AUTHORITY_INPUT_MISSING:{missing}")
    if sha256_file(canonical_path) != contract["canonical_universe_sha256"]:
        raise RuntimeError("CANONICAL_UNIVERSE_HASH_DRIFT")

    canonical = pd.read_csv(canonical_path, dtype=str).fillna("")
    history = pd.read_csv(history_path, low_memory=False)
    current_authority = pd.read_csv(current_authority_path, dtype=str).fillna("")
    current_blocked = pd.read_csv(current_blocked_path, dtype=str).fillna("")

    if len(canonical) != int(contract["expected_product_count"]):
        raise RuntimeError(f"CANONICAL_COUNT_DRIFT:{len(canonical)}")
    if len(history) != int(contract["expected_canonical_historical_rows"]):
        raise RuntimeError(f"CANONICAL_HISTORY_ROW_COUNT_DRIFT:{len(history)}")

    required_history_columns = {
        "canonical_product_id",
        "observation_timestamp",
        "canonical_historical_price",
    }
    missing_history_columns = sorted(required_history_columns - set(history.columns))
    if missing_history_columns:
        raise RuntimeError(f"CANONICAL_HISTORY_SCHEMA_DRIFT:{missing_history_columns}")
    history = history.rename(columns={"canonical_historical_price": "historical_price"})

    history["observation_timestamp"] = pd.to_datetime(history["observation_timestamp"], utc=True, errors="coerce")
    history["historical_price"] = pd.to_numeric(history["historical_price"], errors="coerce")
    invalid_history = history[history["observation_timestamp"].isna() | history["historical_price"].le(0)]
    if not invalid_history.empty:
        raise RuntimeError(f"INVALID_CANONICAL_HISTORY_ROWS:{len(invalid_history)}")
    if history.duplicated(["canonical_product_id", "observation_timestamp"]).any():
        raise RuntimeError("DUPLICATE_CANONICAL_PRODUCT_TIMESTAMP")

    cutoff = pd.Timestamp.now(tz="UTC")
    future_rows = history[history["observation_timestamp"] > cutoff]
    if not future_rows.empty:
        raise RuntimeError(f"FUTURE_HISTORICAL_ROWS:{len(future_rows)}")

    history = history.sort_values(["canonical_product_id", "observation_timestamp"], kind="stable")
    authority = history.groupby("canonical_product_id", as_index=False).agg(
        historical_rows=("historical_price", "size"),
        distinct_observation_dates=("observation_timestamp", "nunique"),
        first_observation=("observation_timestamp", "min"),
        last_observation=("observation_timestamp", "max"),
        minimum_historical_price=("historical_price", "min"),
        maximum_historical_price=("historical_price", "max"),
        latest_historical_price=("historical_price", "last"),
    )
    authority["history_span_days"] = (
        authority["last_observation"] - authority["first_observation"]
    ).dt.total_seconds() / 86400
    authority["historical_price_authority_status"] = (
        authority["historical_rows"].ge(int(contract["minimum_history_rows"]))
        & authority["distinct_observation_dates"].ge(int(contract["minimum_distinct_dates"]))
    ).map({True: "HISTORICAL_PRICE_AUTHORIZED", False: "HISTORICAL_PRICE_BLOCKED"})

    base = canonical[["canonical_product_id", "governed_asset_key", "product_name", "release_date"]].copy()
    eligibility = base.merge(authority, on="canonical_product_id", how="left", validate="one_to_one")
    eligibility["historical_price_authority_status"] = eligibility["historical_price_authority_status"].fillna("HISTORICAL_PRICE_BLOCKED")
    eligibility["historical_rows"] = pd.to_numeric(eligibility["historical_rows"], errors="coerce").fillna(0).astype(int)
    eligibility["distinct_observation_dates"] = pd.to_numeric(eligibility["distinct_observation_dates"], errors="coerce").fillna(0).astype(int)

    current_ids = set(current_authority["canonical_product_id"].astype(str))
    blocked_ids = set(current_blocked["canonical_product_id"].astype(str))
    if current_ids & blocked_ids:
        raise RuntimeError("CURRENT_PRICE_AUTHORITY_OVERLAP")
    if len(current_ids | blocked_ids) != int(contract["expected_product_count"]):
        raise RuntimeError("CURRENT_PRICE_AUTHORITY_RECONCILIATION_FAILED")

    eligibility["current_price_status"] = eligibility["canonical_product_id"].map(
        lambda value: "CURRENT_PRICE_AUTHORIZED" if value in current_ids else "CURRENT_PRICE_BLOCKED"
    )
    eligibility["historical_price_status"] = eligibility["historical_price_authority_status"]

    reasons: list[str] = []
    categories: list[str] = []
    model_status: list[str] = []
    for _, row in eligibility.iterrows():
        current_ok = row["current_price_status"] == "CURRENT_PRICE_AUTHORIZED"
        history_ok = row["historical_price_status"] == "HISTORICAL_PRICE_AUTHORIZED"
        row_reasons: list[str] = []
        if not current_ok:
            row_reasons.append("CURRENT_PRICE_AUTHORITY_REQUIRED")
        if not history_ok:
            row_reasons.append("HISTORICAL_PRICE_AUTHORITY_REQUIRED")
        reasons.append(";".join(row_reasons))
        if current_ok and history_ok:
            categories.append("CURRENT_AND_HISTORY_AUTHORIZED")
            model_status.append("MODEL_INPUT_CANDIDATE")
        elif current_ok:
            categories.append("CURRENT_ONLY")
            model_status.append("MODEL_INPUT_BLOCKED")
        elif history_ok:
            categories.append("HISTORY_ONLY")
            model_status.append("MODEL_INPUT_BLOCKED")
        else:
            categories.append("NEITHER_AUTHORIZED")
            model_status.append("MODEL_INPUT_BLOCKED")
    eligibility["authority_combination"] = categories
    eligibility["model_input_status"] = model_status
    eligibility["model_input_blocking_reasons"] = reasons
    eligibility["forecast_authorized"] = False
    eligibility["ranking_authorized"] = False
    eligibility["purchase_recommendation_authorized"] = False
    eligibility["automatic_execution_authorized"] = False

    blocked = eligibility[eligibility["historical_price_status"].eq("HISTORICAL_PRICE_BLOCKED")].copy()
    authority_rows = eligibility[eligibility["historical_price_status"].eq("HISTORICAL_PRICE_AUTHORIZED")].copy()

    combination_counts = eligibility["authority_combination"].value_counts().to_dict()
    coverage = pd.DataFrame([
        {"metric": "canonical_products", "value": len(eligibility)},
        {"metric": "historical_price_authorized", "value": len(authority_rows)},
        {"metric": "historical_price_blocked", "value": len(blocked)},
        {"metric": "current_and_history_authorized", "value": combination_counts.get("CURRENT_AND_HISTORY_AUTHORIZED", 0)},
        {"metric": "current_only", "value": combination_counts.get("CURRENT_ONLY", 0)},
        {"metric": "history_only", "value": combination_counts.get("HISTORY_ONLY", 0)},
        {"metric": "neither_authorized", "value": combination_counts.get("NEITHER_AUTHORIZED", 0)},
    ])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    authority_output = OUTPUT_DIR / outputs["historical_authority_csv"]
    eligibility_output = OUTPUT_DIR / outputs["model_eligibility_csv"]
    blocked_output = OUTPUT_DIR / outputs["blocked_products_csv"]
    coverage_output = OUTPUT_DIR / outputs["coverage_summary_csv"]
    authority_rows.to_csv(authority_output, index=False)
    eligibility.to_csv(eligibility_output, index=False)
    blocked.to_csv(blocked_output, index=False)
    coverage.to_csv(coverage_output, index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_product_rows": len(eligibility),
        "canonical_historical_rows": len(history),
        "historical_price_authorized_rows": len(authority_rows),
        "historical_price_blocked_rows": len(blocked),
        "current_and_history_authorized_rows": combination_counts.get("CURRENT_AND_HISTORY_AUTHORIZED", 0),
        "current_only_rows": combination_counts.get("CURRENT_ONLY", 0),
        "history_only_rows": combination_counts.get("HISTORY_ONLY", 0),
        "neither_authorized_rows": combination_counts.get("NEITHER_AUTHORIZED", 0),
        "model_input_candidate_rows": int(eligibility["model_input_status"].eq("MODEL_INPUT_CANDIDATE").sum()),
        "historical_append_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    summary_path = OUTPUT_DIR / outputs["summary_json"]
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "history_contract_sha256": sha256_file(HISTORY_CONTRACT_PATH),
        "current_contract_sha256": sha256_file(CURRENT_CONTRACT_PATH),
        "canonical_universe_sha256": sha256_file(canonical_path),
        "canonical_history_sha256": sha256_file(history_path),
        "current_price_authority_sha256": sha256_file(current_authority_path),
        "current_price_blocked_sha256": sha256_file(current_blocked_path),
        "historical_authority_sha256": sha256_file(authority_output),
        "model_eligibility_sha256": sha256_file(eligibility_output),
        "blocked_products_sha256": sha256_file(blocked_output),
        "coverage_summary_sha256": sha256_file(coverage_output),
        "scope_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW_BUILD")
    print(f"CANONICAL_PRODUCT_ROWS={len(eligibility)}")
    print(f"CANONICAL_HISTORICAL_ROWS={len(history)}")
    print(f"HISTORICAL_PRICE_AUTHORIZED_ROWS={len(authority_rows)}")
    print(f"HISTORICAL_PRICE_BLOCKED_ROWS={len(blocked)}")
    print(f"CURRENT_AND_HISTORY_AUTHORIZED_ROWS={summary['current_and_history_authorized_rows']}")
    print(f"CURRENT_ONLY_ROWS={summary['current_only_rows']}")
    print(f"HISTORY_ONLY_ROWS={summary['history_only_rows']}")
    print(f"NEITHER_AUTHORIZED_ROWS={summary['neither_authorized_rows']}")
    print(f"MODEL_INPUT_CANDIDATE_ROWS={summary['model_input_candidate_rows']}")
    print("NEXT_STAGE=PRECOLLECTOR_SUPPLY_AND_LIQUIDITY_AUTHORITY")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
