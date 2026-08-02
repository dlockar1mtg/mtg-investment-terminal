"""Trace the raw lineage of the universal MTG price-history foundation used by Collector V1."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data/operations/mtg_history_foundation/universal_mtg_price_history.csv"
CONTRACT = ROOT / "config/mtg/standards/collector_history_foundation_lineage_contract_v1.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_history_foundation_lineage"

TEXT_EXTENSIONS = {".py", ".ps1", ".sql", ".json", ".yaml", ".yml", ".toml", ".md", ".txt"}
DATA_EXTENSIONS = {".csv", ".jsonl", ".parquet"}
EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__", "node_modules"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("/", "\\")


def excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def read_columns(path: Path) -> list[str]:
    try:
        if path.suffix.lower() == ".csv":
            return list(pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns)
        if path.suffix.lower() == ".jsonl":
            frame = pd.read_json(path, lines=True, nrows=1)
            return list(frame.columns)
        if path.suffix.lower() == ".parquet":
            return list(pd.read_parquet(path).columns)
    except Exception:
        return []
    return []


def first_present(columns: list[str], candidates: list[str]) -> str:
    lowered = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [str(path) for path in (TARGET, CONTRACT) if not path.is_file()]
    if missing:
        print(json.dumps({"status": "FAIL_REQUIRED_INPUTS_MISSING", "missing": missing}, indent=2))
        return 1 if args.strict else 0

    target_columns = read_columns(TARGET)
    target_hash = sha256(TARGET)
    candidate_rows: list[dict[str, object]] = []
    reference_rows: list[dict[str, object]] = []

    target_terms = [
        "universal_mtg_price_history.csv",
        "universal_mtg_price_history",
        "mtg_history_foundation",
    ]
    writer_terms = ["to_csv", "write_csv", "copyfile", "shutil.copy", "write_text", "universal_mtg_price_history"]

    for path in ROOT.rglob("*"):
        if not path.is_file() or excluded(path):
            continue
        suffix = path.suffix.lower()
        if suffix in TEXT_EXTENSIONS:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            matched = [term for term in target_terms if term.lower() in text.lower()]
            if matched:
                writer = any(term.lower() in text.lower() for term in writer_terms)
                reference_rows.append({
                    "reference_path": rel(path),
                    "matched_terms": "|".join(matched),
                    "writer_signal": writer,
                })

        if suffix not in DATA_EXTENSIONS or path == TARGET:
            continue
        columns = read_columns(path)
        if not columns:
            continue
        identity = first_present(columns, ["tcgplayer_product_id", "resolved_tcgplayer_product_id", "product_id", "investment_product_id"])
        date = first_present(columns, ["observation_date", "date", "price_date", "snapshot_date", "as_of_date", "observed_at", "observed_at_utc", "collected_at"])
        price = first_present(columns, ["market_price", "price", "value", "market", "median_price", "low_price", "asking_price", "listing_price"])
        source = first_present(columns, ["source", "source_name", "provider", "marketplace", "data_source"])
        if not (identity and date and price):
            continue
        path_text = rel(path).lower()
        likely_copy = any(token in path_text for token in ["backup", "repair_input", "archive", "staging", "certification", "copy", "migration"])
        consolidated = any(token in path_text for token in ["consolidated", "canonical", "foundation", "summary", "metrics", "features"])
        raw_observation_candidate = not consolidated and not likely_copy
        candidate_rows.append({
            "candidate_path": rel(path),
            "source_sha256": sha256(path),
            "column_count": len(columns),
            "schema_overlap_ratio": round(len(set(columns) & set(target_columns)) / max(1, len(set(target_columns))), 6),
            "identity_field": identity,
            "date_field": date,
            "price_field": price,
            "source_field": source,
            "likely_copy_or_promoted_artifact": likely_copy,
            "consolidated_or_derived_candidate": consolidated,
            "raw_observation_candidate": raw_observation_candidate,
        })

    candidates = pd.DataFrame(candidate_rows)
    references = pd.DataFrame(reference_rows)
    candidates_path = OUT / "collector_history_foundation_lineage_candidates.csv"
    references_path = OUT / "collector_history_foundation_code_references.csv"
    candidates.to_csv(candidates_path, index=False)
    references.to_csv(references_path, index=False)

    writer_count = int(references["writer_signal"].sum()) if not references.empty else 0
    raw_count = int(candidates["raw_observation_candidate"].sum()) if not candidates.empty else 0
    summary = {
        "block_name": "Collector V1 History Foundation Lineage Trace",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_path": rel(TARGET),
        "target_sha256": target_hash,
        "target_column_count": len(target_columns),
        "candidate_source_count": int(len(candidates)),
        "raw_observation_candidate_count": raw_count,
        "code_reference_count": int(len(references)),
        "writer_reference_count": writer_count,
        "lineage_state": "FOUNDATION_LINEAGE_PARTIALLY_RECONSTRUCTED" if writer_count or raw_count else "FOUNDATION_LINEAGE_UNRESOLVED",
        "raw_historical_price_authority_certified": False,
        "authority_reason": "Discovery does not certify authority; a writer transformation and its raw point-in-time inputs must be reproduced and reconciled to the target history.",
        "candidate_path": rel(candidates_path),
        "candidate_sha256": sha256(candidates_path),
        "reference_path": rel(references_path),
        "reference_sha256": sha256(references_path),
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": [],
        "status": "PASS_COLLECTOR_V1_HISTORY_FOUNDATION_LINEAGE_TRACE",
    }
    summary_path = OUT / "collector_history_foundation_lineage_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
