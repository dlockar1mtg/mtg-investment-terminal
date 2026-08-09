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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_historical_price_evidence_inventory_contract_v1.json"
FREEZE_BUILDER = ROOT / "scripts/build_precollector_canonical_universe_freeze.py"
FREEZE_DIR = ROOT / "artifacts/precollector/canonical_universe_freeze"
OUTPUT_DIR = ROOT / "artifacts/precollector/historical_price_evidence_inventory"


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
        found = lower.get(name.casefold())
        if found:
            return found
    return None


def run_freeze_builder() -> None:
    completed = subprocess.run([sys.executable, str(FREEZE_BUILDER)], cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"CANONICAL_FREEZE_REBUILD_FAILED: {completed.returncode}")


def inspect_csv(path: Path, canonical_ids: set[str], contract: dict) -> tuple[dict, list[dict]]:
    relative = path.relative_to(ROOT).as_posix()
    base = {
        "relative_path": relative,
        "file_sha256": sha256_file(path),
        "read_status": "PASS",
        "row_count": 0,
        "column_count": 0,
        "identity_column": "",
        "date_column": "",
        "price_column": "",
        "canonical_overlap_products": 0,
        "positive_price_rows": 0,
        "valid_date_rows": 0,
        "candidate_status": "NOT_CANDIDATE",
        "blocking_reasons": "",
    }
    coverage_rows: list[dict] = []
    try:
        frame = pd.read_csv(path, low_memory=False)
    except Exception as exc:
        base["read_status"] = "FAILED"
        base["blocking_reasons"] = f"CSV_READ_FAILED:{type(exc).__name__}"
        return base, coverage_rows

    base["row_count"] = int(len(frame))
    base["column_count"] = int(len(frame.columns))
    columns = [str(column) for column in frame.columns]
    id_col = first_column(columns, contract["accepted_identity_columns"])
    date_col = first_column(columns, contract["accepted_date_columns"])
    price_col = first_column(columns, contract["accepted_price_columns"])
    base["identity_column"] = id_col or ""
    base["date_column"] = date_col or ""
    base["price_column"] = price_col or ""

    reasons: list[str] = []
    if id_col is None:
        reasons.append("IDENTITY_COLUMN_MISSING")
    if date_col is None:
        reasons.append("DATE_COLUMN_MISSING")
    if price_col is None:
        reasons.append("PRICE_COLUMN_MISSING")

    if id_col and date_col and price_col:
        work = pd.DataFrame({
            "product_id": frame[id_col].map(normalize_id),
            "observation_date": pd.to_datetime(frame[date_col], utc=True, errors="coerce"),
            "price": pd.to_numeric(frame[price_col], errors="coerce"),
        })
        work = work[work["product_id"].isin(canonical_ids)].copy()
        base["canonical_overlap_products"] = int(work["product_id"].nunique())
        base["positive_price_rows"] = int(work["price"].gt(0).sum())
        base["valid_date_rows"] = int(work["observation_date"].notna().sum())
        valid = work[work["price"].gt(0) & work["observation_date"].notna()].copy()
        if valid.empty:
            reasons.append("NO_VALID_CANONICAL_HISTORY_ROWS")
        else:
            grouped = valid.groupby("product_id", as_index=False).agg(
                historical_rows=("price", "size"),
                first_observation=("observation_date", "min"),
                last_observation=("observation_date", "max"),
            )
            for _, row in grouped.iterrows():
                coverage_rows.append({
                    "relative_path": relative,
                    "canonical_product_id": f"tcgplayer:{row['product_id']}",
                    "historical_rows": int(row["historical_rows"]),
                    "first_observation": row["first_observation"].isoformat(),
                    "last_observation": row["last_observation"].isoformat(),
                })
            if len(valid) < int(contract["minimum_positive_rows_for_candidate"]):
                reasons.append("INSUFFICIENT_POSITIVE_HISTORY_ROWS")

    base["blocking_reasons"] = ";".join(reasons)
    base["candidate_status"] = "HISTORICAL_EVIDENCE_CANDIDATE" if not reasons else "NOT_CANDIDATE"
    return base, coverage_rows


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)
    run_freeze_builder()

    canonical_path = FREEZE_DIR / "precollector_canonical_product_universe_v1.csv"
    if not canonical_path.is_file():
        raise RuntimeError("CANONICAL_UNIVERSE_INPUT_MISSING")
    if sha256_file(canonical_path) != contract["canonical_universe_sha256"]:
        raise RuntimeError("CANONICAL_UNIVERSE_HASH_DRIFT")
    canonical = pd.read_csv(canonical_path, dtype=str).fillna("")
    if len(canonical) != int(contract["expected_product_count"]):
        raise RuntimeError(f"CANONICAL_COUNT_DRIFT: {len(canonical)}")
    canonical_ids = set(canonical["canonical_product_id"].map(normalize_id))

    inventory_rows: list[dict] = []
    coverage_rows: list[dict] = []
    excluded_markers = [str(value).casefold() for value in contract["excluded_path_markers"]]
    seen: set[Path] = set()
    for root_name in contract["scan_roots"]:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            resolved = path.resolve()
            relative = path.relative_to(ROOT).as_posix()
            if resolved in seen or any(marker in relative.casefold() for marker in excluded_markers):
                continue
            seen.add(resolved)
            inventory, coverage = inspect_csv(path, canonical_ids, contract)
            inventory_rows.append(inventory)
            coverage_rows.extend(coverage)

    inventory = pd.DataFrame(inventory_rows)
    if inventory.empty:
        raise RuntimeError("NO_CSV_FILES_DISCOVERED")
    candidates = inventory[inventory["candidate_status"].eq("HISTORICAL_EVIDENCE_CANDIDATE")].copy()
    coverage = pd.DataFrame(coverage_rows)
    if coverage.empty:
        coverage = pd.DataFrame(columns=["relative_path", "canonical_product_id", "historical_rows", "first_observation", "last_observation"])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    inventory_path = OUTPUT_DIR / outputs["inventory_csv"]
    candidates_path = OUTPUT_DIR / outputs["candidate_sources_csv"]
    coverage_path = OUTPUT_DIR / outputs["product_coverage_csv"]
    inventory.sort_values(["candidate_status", "canonical_overlap_products", "relative_path"], ascending=[True, False, True]).to_csv(inventory_path, index=False)
    candidates.sort_values(["canonical_overlap_products", "positive_price_rows", "relative_path"], ascending=[False, False, True]).to_csv(candidates_path, index=False)
    coverage.sort_values(["canonical_product_id", "relative_path"]).to_csv(coverage_path, index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_HISTORICAL_PRICE_EVIDENCE_INVENTORY_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_product_rows": len(canonical),
        "csv_files_scanned": len(inventory),
        "historical_candidate_source_rows": len(candidates),
        "candidate_covered_products": int(coverage["canonical_product_id"].nunique()) if not coverage.empty else 0,
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
        "inventory_sha256": sha256_file(inventory_path),
        "candidate_sources_sha256": sha256_file(candidates_path),
        "product_coverage_sha256": sha256_file(coverage_path),
        "scope_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_HISTORICAL_PRICE_EVIDENCE_INVENTORY_BUILD")
    print(f"CANONICAL_PRODUCT_ROWS={len(canonical)}")
    print(f"CSV_FILES_SCANNED={len(inventory)}")
    print(f"HISTORICAL_CANDIDATE_SOURCE_ROWS={len(candidates)}")
    print(f"CANDIDATE_COVERED_PRODUCTS={summary['candidate_covered_products']}")
    print("NEXT_STAGE=PRECOLLECTOR_HISTORICAL_SOURCE_ADJUDICATION")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
