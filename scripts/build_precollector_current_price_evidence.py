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
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_current_price_evidence_contract_v1.json"
FREEZE_BUILDER = ROOT / "scripts/build_precollector_canonical_universe_freeze.py"
FREEZE_DIR = ROOT / "artifacts/precollector/canonical_universe_freeze"
OUTPUT_DIR = ROOT / "artifacts/precollector/current_price_evidence"


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
    by_lower = {str(column).casefold(): str(column) for column in frame.columns}
    for name in names:
        if name in frame.columns:
            return name
        found = by_lower.get(name.casefold())
        if found:
            return found
    return None


def run_freeze_builder() -> None:
    completed = subprocess.run([sys.executable, str(FREEZE_BUILDER)], cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"CANONICAL_FREEZE_REBUILD_FAILED: {completed.returncode}")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    precollector_root = ROOT / "artifacts/precollector"
    if precollector_root.exists():
        shutil.rmtree(precollector_root)
    run_freeze_builder()

    canonical_path = FREEZE_DIR / "precollector_canonical_product_universe_v1.csv"
    source_path = ROOT / contract["source_snapshot"]
    if not canonical_path.is_file():
        raise RuntimeError("CANONICAL_UNIVERSE_INPUT_MISSING")
    if not source_path.is_file():
        raise RuntimeError("TCGCSV_SOURCE_SNAPSHOT_MISSING")
    if sha256_file(canonical_path) != contract["canonical_universe_sha256"]:
        raise RuntimeError("CANONICAL_UNIVERSE_HASH_DRIFT")

    canonical = pd.read_csv(canonical_path, dtype=str).fillna("")
    source = pd.read_csv(source_path, low_memory=False)
    if len(canonical) != int(contract["expected_product_count"]):
        raise RuntimeError(f"CANONICAL_COUNT_DRIFT: {len(canonical)}")

    source_id_col = first_column(source, ["productId", "product_id", "tcgplayer_product_id", "id"])
    if source_id_col is None:
        raise RuntimeError("TCGCSV_PRODUCT_ID_COLUMN_MISSING")
    source = source.copy()
    source["source_product_id"] = source[source_id_col].map(normalize_id)
    source = source[source["source_product_id"].ne("")].drop_duplicates("source_product_id", keep="last")

    evidence = canonical.copy()
    evidence["source_product_id"] = evidence["canonical_product_id"].map(normalize_id)

    selected_source_columns: list[str] = ["source_product_id"]
    name_col = first_column(source, ["name", "productName", "product_name"])
    group_col = first_column(source, ["groupId", "group_id", "tcgcsv_group_id"])
    modified_col = first_column(source, ["modifiedOn", "modified_on", "updatedAt", "updated_at"])
    if name_col:
        source = source.rename(columns={name_col: "source_product_name"})
        selected_source_columns.append("source_product_name")
    if group_col:
        source = source.rename(columns={group_col: "source_group_id"})
        selected_source_columns.append("source_group_id")
    if modified_col:
        source = source.rename(columns={modified_col: "source_modified_on"})
        selected_source_columns.append("source_modified_on")

    discovered_prices: list[str] = []
    for governed_name in contract["accepted_price_fields"]:
        column = first_column(source, [governed_name])
        if column:
            output_name = f"source_{governed_name}"
            source = source.rename(columns={column: output_name})
            selected_source_columns.append(output_name)
            discovered_prices.append(output_name)

    evidence = evidence.merge(source[selected_source_columns], on="source_product_id", how="left", validate="one_to_one")
    evidence["identity_match"] = evidence.get("source_product_name", pd.Series("", index=evidence.index)).fillna("").astype(str).str.strip().ne("")

    for column in discovered_prices:
        evidence[column] = pd.to_numeric(evidence[column], errors="coerce")
    if discovered_prices:
        evidence["positive_price_count"] = evidence[discovered_prices].gt(0).sum(axis=1)
        evidence["governed_current_price"] = evidence[discovered_prices].where(evidence[discovered_prices].gt(0)).bfill(axis=1).iloc[:, 0]
        evidence["governed_price_field"] = evidence[discovered_prices].gt(0).idxmax(axis=1).str.removeprefix("source_")
        evidence.loc[evidence["positive_price_count"].eq(0), "governed_price_field"] = ""
    else:
        evidence["positive_price_count"] = 0
        evidence["governed_current_price"] = pd.NA
        evidence["governed_price_field"] = ""

    reasons: list[str] = []
    for _, row in evidence.iterrows():
        row_reasons: list[str] = []
        if not bool(row["identity_match"]):
            row_reasons.append("SOURCE_PRODUCT_ID_NOT_FOUND")
        if int(row["positive_price_count"]) <= 0:
            row_reasons.append("POSITIVE_CURRENT_PRICE_NOT_FOUND")
        reasons.append(";".join(row_reasons))
    evidence["blocking_reasons"] = reasons
    evidence["current_price_evidence_status"] = evidence["blocking_reasons"].eq("").map({True: "CURRENT_PRICE_CANDIDATE", False: "BLOCKED"})
    evidence["historical_append_authorized"] = False
    evidence["forecast_authorized"] = False
    evidence["ranking_authorized"] = False
    evidence["purchase_recommendation_authorized"] = False

    candidates = evidence[evidence["current_price_evidence_status"].eq("CURRENT_PRICE_CANDIDATE")].copy()
    blocked = evidence[evidence["current_price_evidence_status"].eq("BLOCKED")].copy()
    coverage = pd.DataFrame([
        {"metric": "canonical_products", "value": len(evidence)},
        {"metric": "source_identity_matches", "value": int(evidence["identity_match"].sum())},
        {"metric": "current_price_candidates", "value": len(candidates)},
        {"metric": "blocked_products", "value": len(blocked)},
        {"metric": "products_with_positive_price", "value": int(evidence["positive_price_count"].gt(0).sum())},
    ])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = contract["outputs"]
    paths = {
        "all": OUTPUT_DIR / outputs["all_evidence_csv"],
        "candidate": OUTPUT_DIR / outputs["candidate_csv"],
        "blocked": OUTPUT_DIR / outputs["blocked_csv"],
        "coverage": OUTPUT_DIR / outputs["coverage_csv"],
    }
    evidence.to_csv(paths["all"], index=False)
    candidates.to_csv(paths["candidate"], index=False)
    blocked.to_csv(paths["blocked"], index=False)
    coverage.to_csv(paths["coverage"], index=False)

    summary = {
        "certification_status": "PASS_PRECOLLECTOR_CURRENT_PRICE_EVIDENCE_BUILD",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_product_rows": len(evidence),
        "source_identity_match_rows": int(evidence["identity_match"].sum()),
        "current_price_candidate_rows": len(candidates),
        "blocked_rows": len(blocked),
        "discovered_price_fields": discovered_prices,
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
        "all_evidence_sha256": sha256_file(paths["all"]),
        "candidate_sha256": sha256_file(paths["candidate"]),
        "blocked_sha256": sha256_file(paths["blocked"]),
        "coverage_sha256": sha256_file(paths["coverage"]),
        "scope_mutation_detected": False,
    }
    (OUTPUT_DIR / outputs["manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_CURRENT_PRICE_EVIDENCE_BUILD")
    print(f"CANONICAL_PRODUCT_ROWS={len(evidence)}")
    print(f"SOURCE_IDENTITY_MATCH_ROWS={int(evidence['identity_match'].sum())}")
    print(f"CURRENT_PRICE_CANDIDATE_ROWS={len(candidates)}")
    print(f"BLOCKED_ROWS={len(blocked)}")
    print(f"DISCOVERED_PRICE_FIELDS={','.join(discovered_prices)}")
    print("NEXT_STAGE=PRECOLLECTOR_LIVE_CURRENT_PRICE_COLLECTION")
    print("HISTORICAL_APPEND_AUTHORIZED=FALSE")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
