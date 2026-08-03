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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_historical_source_adjudication_contract_v1.json"
INVENTORY_BUILDER = ROOT / "scripts/build_precollector_historical_price_evidence_inventory.py"
INVENTORY_DIR = ROOT / "artifacts/precollector/historical_price_evidence_inventory"
FREEZE_DIR = ROOT / "artifacts/precollector/canonical_universe_freeze"
OUTPUT_DIR = ROOT / "artifacts/precollector/historical_source_adjudication"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_id(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if text.startswith("tcgplayer:"):
        text = text.split(":", 1)[1]
    return text


def first_column(columns: list[str], accepted: list[str]) -> str | None:
    lower = {str(column).casefold(): str(column) for column in columns}
    for name in accepted:
        if name in columns:
            return name
        if name.casefold() in lower:
            return lower[name.casefold()]
    return None


def run_inventory() -> None:
    completed = subprocess.run([sys.executable, str(INVENTORY_BUILDER)], cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"HISTORICAL_INVENTORY_REBUILD_FAILED: {completed.returncode}")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)
    run_inventory()

    candidates_path = INVENTORY_DIR / "precollector_historical_candidate_sources_v1.csv"
    canonical_path = FREEZE_DIR / "precollector_canonical_product_universe_v1.csv"
    if not candidates_path.is_file() or not canonical_path.is_file():
        raise RuntimeError("ADJUDICATION_INPUT_MISSING")
    if sha256_file(canonical_path) != contract["canonical_universe_sha256"]:
        raise RuntimeError("CANONICAL_UNIVERSE_HASH_DRIFT")

    candidates = pd.read_csv(candidates_path, dtype=str).fillna("")
    canonical = pd.read_csv(canonical_path, dtype=str).fillna("")
    if len(candidates) != int(contract["expected_candidate_source_count"]):
        raise RuntimeError(f"CANDIDATE_SOURCE_COUNT_DRIFT: {len(candidates)}")
    canonical_ids = set(canonical["canonical_product_id"].map(normalize_id))

    source_rows: list[dict] = []
    audit_frames: list[pd.DataFrame] = []
    coverage_frames: list[pd.DataFrame] = []

    for _, candidate in candidates.iterrows():
        relative = str(candidate["relative_path"])
        path = ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"CANDIDATE_SOURCE_MISSING: {relative}")
        frame = pd.read_csv(path, low_memory=False)
        columns = [str(column) for column in frame.columns]
        id_col = first_column(columns, contract["accepted_identity_columns"])
        date_col = first_column(columns, contract["accepted_date_columns"])
        price_col = first_column(columns, contract["accepted_price_columns"])
        if not id_col or not date_col or not price_col:
            raise RuntimeError(f"CANDIDATE_SCHEMA_DRIFT: {relative}")

        work = pd.DataFrame({
            "source_path": relative,
            "canonical_product_id": frame[id_col].map(normalize_id).map(lambda value: f"tcgplayer:{value}" if value else ""),
            "observation_timestamp": pd.to_datetime(frame[date_col], utc=True, errors="coerce"),
            "historical_price": pd.to_numeric(frame[price_col], errors="coerce"),
        })
        work["canonical_identity_match"] = work["canonical_product_id"].map(normalize_id).isin(canonical_ids)
        work["valid_timestamp"] = work["observation_timestamp"].notna()
        work["positive_price"] = work["historical_price"].gt(0)
        work["row_admissible"] = work["canonical_identity_match"] & work["valid_timestamp"] & work["positive_price"]
        admissible = work[work["row_admissible"]].copy()
        duplicate_count = int(admissible.duplicated(["canonical_product_id", "observation_timestamp"]).sum())
        admissible = admissible.drop_duplicates(["canonical_product_id", "observation_timestamp"], keep="last")

        coverage = admissible.groupby("canonical_product_id", as_index=False).agg(
            historical_rows=("historical_price", "size"),
            distinct_observation_dates=("observation_timestamp", "nunique"),
            first_observation=("observation_timestamp", "min"),
            last_observation=("observation_timestamp", "max"),
        )
        coverage["source_path"] = relative
        coverage["product_history_status"] = (
            (coverage["historical_rows"] >= int(contract["minimum_rows_per_covered_product"]))
            & (coverage["distinct_observation_dates"] >= int(contract["minimum_distinct_observation_dates"]))
        ).map({True: "PRODUCT_HISTORY_ADMISSIBLE", False: "PRODUCT_HISTORY_INSUFFICIENT"})

        reasons: list[str] = []
        if admissible.empty:
            reasons.append("NO_ADMISSIBLE_ROWS")
        if duplicate_count:
            reasons.append("DUPLICATE_PRODUCT_TIMESTAMP_ROWS_PRESENT")
        admissible_products = int(coverage["product_history_status"].eq("PRODUCT_HISTORY_ADMISSIBLE").sum()) if not coverage.empty else 0
        if admissible_products == 0:
            reasons.append("NO_PRODUCTS_WITH_MINIMUM_HISTORY_DEPTH")

        source_rows.append({
            "relative_path": relative,
            "source_sha256": sha256_file(path),
            "input_rows": len(frame),
            "admissible_rows": len(admissible),
            "covered_products": int(admissible["canonical_product_id"].nunique()),
            "products_with_minimum_history_depth": admissible_products,
            "duplicate_product_timestamp_rows": duplicate_count,
            "first_observation": admissible["observation_timestamp"].min().isoformat() if not admissible.empty else "",
            "last_observation": admissible["observation_timestamp"].max().isoformat() if not admissible.empty else "",
            "adjudication_status": "SOURCE_ADMISSIBLE" if not reasons else "SOURCE_REVIEW_REQUIRED",
            "blocking_reasons": ";".join(reasons),
        })
        audit_frames.append(work)
        coverage_frames.append(coverage)

    source_adjudication = pd.DataFrame(source_rows)
    row_audit = pd.concat(audit_frames, ignore_index=True)
    product_coverage = pd.concat(coverage_frames, ignore_index=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    source_path = OUTPUT_DIR / outputs["source_adjudication_csv"]
    audit_path = OUTPUT_DIR / outputs["row_level_audit_csv"]
    coverage_path = OUTPUT_DIR / outputs["product_coverage_csv"]
    source_adjudication.to_csv(source_path, index=False)
    row_audit.to_csv(audit_path, index=False)
    product_coverage.to_csv(coverage_path, index=False)

    admissible_sources = int(source_adjudication["adjudication_status"].eq("SOURCE_ADMISSIBLE").sum())
    covered_products = int(product_coverage.loc[product_coverage["product_history_status"].eq("PRODUCT_HISTORY_ADMISSIBLE"), "canonical_product_id"].nunique())
    summary = {
        "certification_status": "PASS_PRECOLLECTOR_HISTORICAL_SOURCE_ADJUDICATION_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_source_rows": len(source_adjudication),
        "source_admissible_rows": admissible_sources,
        "source_review_required_rows": len(source_adjudication) - admissible_sources,
        "adjudicated_covered_products": covered_products,
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
        "canonical_universe_sha256": sha256_file(canonical_path),
        "candidate_sources_sha256": sha256_file(candidates_path),
        "source_adjudication_sha256": sha256_file(source_path),
        "row_level_audit_sha256": sha256_file(audit_path),
        "product_coverage_sha256": sha256_file(coverage_path),
        "scope_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_HISTORICAL_SOURCE_ADJUDICATION_BUILD")
    print(f"CANDIDATE_SOURCE_ROWS={len(source_adjudication)}")
    print(f"SOURCE_ADMISSIBLE_ROWS={admissible_sources}")
    print(f"SOURCE_REVIEW_REQUIRED_ROWS={len(source_adjudication) - admissible_sources}")
    print(f"ADJUDICATED_COVERED_PRODUCTS={covered_products}")
    print("NEXT_STAGE=PRECOLLECTOR_CANONICAL_HISTORICAL_PRICE_BUILD")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
