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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_live_current_price_collection_contract_v1.json"
EVIDENCE_BUILDER = ROOT / "scripts/build_precollector_current_price_evidence.py"
EVIDENCE_DIR = ROOT / "artifacts/precollector/current_price_evidence"
FREEZE_DIR = ROOT / "artifacts/precollector/canonical_universe_freeze"
OUTPUT_DIR = ROOT / "artifacts/precollector/live_current_price_collection"


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


def first_column(frame: pd.DataFrame, names: list[str]) -> str | None:
    lowered = {str(column).casefold(): str(column) for column in frame.columns}
    for name in names:
        if name in frame.columns:
            return name
        found = lowered.get(name.casefold())
        if found:
            return found
    return None


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"SUBPROCESS_FAILED: {completed.returncode}: {' '.join(command)}")


def build_product_map(canonical: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    id_col = first_column(source, ["productId", "product_id", "tcgplayer_product_id", "id"])
    category_col = first_column(source, ["categoryId", "category_id", "tcgcsv_category_id"])
    group_col = first_column(source, ["groupId", "group_id", "tcgcsv_group_id"])
    source_name_col = first_column(source, ["name", "productName", "product_name"])
    if not all([id_col, category_col, group_col]):
        raise RuntimeError("TCGCSV_MAPPING_FIELDS_MISSING")

    mapped_source = pd.DataFrame({
        "tcgplayer_product_id": source[id_col].map(normalize_id),
        "tcgcsv_category_id": source[category_col].map(normalize_id),
        "tcgcsv_group_id": source[group_col].map(normalize_id),
        "source_product_name": source[source_name_col].fillna("").astype(str) if source_name_col else "",
    })
    mapped_source = mapped_source[mapped_source["tcgplayer_product_id"].ne("")]
    mapped_source = mapped_source.drop_duplicates("tcgplayer_product_id", keep="last")

    product_map = pd.DataFrame({
        "box_name": canonical["product_name"].astype(str),
        "tcgplayer_product_id": canonical["canonical_product_id"].map(normalize_id),
        "canonical_product_id": canonical["canonical_product_id"].astype(str),
        "governed_asset_key": canonical["governed_asset_key"].astype(str),
    }).merge(mapped_source, on="tcgplayer_product_id", how="left", validate="one_to_one")

    required = ["box_name", "tcgplayer_product_id", "tcgcsv_category_id", "tcgcsv_group_id"]
    if len(product_map) != 124:
        raise RuntimeError(f"PRODUCT_MAP_COUNT_DRIFT: {len(product_map)}")
    if product_map[required].fillna("").astype(str).apply(lambda column: column.str.strip().eq("")).any().any():
        raise RuntimeError("PRODUCT_MAP_REQUIRED_FIELD_BLANK")
    if product_map["tcgplayer_product_id"].duplicated().any():
        raise RuntimeError("PRODUCT_MAP_DUPLICATE_PRODUCT_ID")
    return product_map.sort_values(["box_name", "tcgplayer_product_id"], kind="stable").reset_index(drop=True)


def classify(observations: pd.DataFrame, product_map: pd.DataFrame, contract: dict) -> pd.DataFrame:
    required = contract["required_observation_columns"]
    missing = [column for column in required if column not in observations.columns]
    if missing:
        raise RuntimeError(f"LIVE_OBSERVATION_COLUMNS_MISSING: {missing}")
    observations = observations.copy()
    observations["tcgplayer_product_id"] = observations["tcgplayer_product_id"].map(normalize_id)
    merged = product_map.merge(observations, on=["box_name", "tcgplayer_product_id"], how="left", validate="one_to_one")
    market = pd.to_numeric(merged["market_price"], errors="coerce")
    timestamps = pd.to_datetime(merged["collected_at"], utc=True, errors="coerce")
    age_hours = (pd.Timestamp.now(tz="UTC") - timestamps).dt.total_seconds() / 3600
    merged["observation_age_hours"] = age_hours
    reasons: list[str] = []
    for index, row in merged.iterrows():
        row_reasons: list[str] = []
        if pd.isna(row.get("retrieval_id")) or not str(row.get("retrieval_id", "")).strip():
            row_reasons.append("LIVE_OBSERVATION_MISSING")
        if str(row.get("price_selection_status", "")) != contract["accepted_selection_status"]:
            row_reasons.append("NORMAL_SUBTYPE_NOT_UNIQUE")
        if str(row.get("admission_status", "")) != contract["accepted_admission_status"]:
            row_reasons.append("SOURCE_ADMISSION_NOT_PRICE_CANDIDATE")
        if pd.isna(market.iloc[index]) or float(market.iloc[index]) <= 0:
            row_reasons.append("POSITIVE_MARKET_PRICE_REQUIRED")
        if pd.isna(age_hours.iloc[index]) or float(age_hours.iloc[index]) > float(contract["maximum_observation_age_hours"]):
            row_reasons.append("LIVE_OBSERVATION_NOT_FRESH")
        reasons.append(";".join(row_reasons))
    merged["blocking_reasons"] = reasons
    merged["current_price_authority_status"] = merged["blocking_reasons"].eq("").map({True: "CURRENT_PRICE_AUTHORITY_CANDIDATE", False: "BLOCKED"})
    merged["historical_append_authorized"] = False
    merged["forecast_authorized"] = False
    merged["ranking_authorized"] = False
    merged["purchase_recommendation_authorized"] = False
    return merged


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)
    run([sys.executable, str(EVIDENCE_BUILDER)])

    canonical_path = FREEZE_DIR / "precollector_canonical_product_universe_v1.csv"
    source_path = ROOT / contract["source_snapshot"]
    if sha256_file(canonical_path) != contract["canonical_universe_sha256"]:
        raise RuntimeError("CANONICAL_UNIVERSE_HASH_DRIFT")
    canonical = pd.read_csv(canonical_path, dtype=str).fillna("")
    source = pd.read_csv(source_path, low_memory=False)
    product_map = build_product_map(canonical, source)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    product_map_path = OUTPUT_DIR / outputs["product_map_csv"]
    observations_path = OUTPUT_DIR / outputs["observations_csv"]
    collection_summary = OUTPUT_DIR / "tcgcsv_collection_summary.json"
    product_map.to_csv(product_map_path, index=False)

    run([sys.executable, "scripts/run_daily_tcgcsv_collection.py", "--product-map", str(product_map_path), "--observations-output", str(observations_path), "--summary-output", str(collection_summary), "--dry-run"])
    run([sys.executable, "scripts/run_daily_tcgcsv_collection.py", "--product-map", str(product_map_path), "--observations-output", str(observations_path), "--summary-output", str(collection_summary)])

    observations = pd.read_csv(observations_path, low_memory=False)
    authority = classify(observations, product_map, contract)
    candidates = authority[authority["current_price_authority_status"].eq("CURRENT_PRICE_AUTHORITY_CANDIDATE")].copy()
    blocked = authority[authority["current_price_authority_status"].eq("BLOCKED")].copy()
    coverage = pd.DataFrame([
        {"metric": "canonical_products", "value": len(product_map)},
        {"metric": "live_observation_rows", "value": len(observations)},
        {"metric": "authority_candidates", "value": len(candidates)},
        {"metric": "blocked_products", "value": len(blocked)},
        {"metric": "positive_market_prices", "value": int(pd.to_numeric(authority["market_price"], errors="coerce").gt(0).sum())},
    ])

    authority_path = OUTPUT_DIR / outputs["authority_csv"]
    blocked_path = OUTPUT_DIR / outputs["blocked_csv"]
    coverage_path = OUTPUT_DIR / outputs["coverage_csv"]
    authority.to_csv(authority_path, index=False)
    blocked.to_csv(blocked_path, index=False)
    coverage.to_csv(coverage_path, index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_LIVE_CURRENT_PRICE_COLLECTION_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_product_rows": len(product_map),
        "live_observation_rows": len(observations),
        "current_price_authority_candidate_rows": len(candidates),
        "blocked_rows": len(blocked),
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
        "source_snapshot_sha256": sha256_file(source_path),
        "product_map_sha256": sha256_file(product_map_path),
        "observations_sha256": sha256_file(observations_path),
        "authority_sha256": sha256_file(authority_path),
        "blocked_sha256": sha256_file(blocked_path),
        "coverage_sha256": sha256_file(coverage_path),
        "scope_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_LIVE_CURRENT_PRICE_COLLECTION_BUILD")
    print(f"CANONICAL_PRODUCT_ROWS={len(product_map)}")
    print(f"LIVE_OBSERVATION_ROWS={len(observations)}")
    print(f"CURRENT_PRICE_AUTHORITY_CANDIDATE_ROWS={len(candidates)}")
    print(f"BLOCKED_ROWS={len(blocked)}")
    print("NEXT_STAGE=PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_REVIEW")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
