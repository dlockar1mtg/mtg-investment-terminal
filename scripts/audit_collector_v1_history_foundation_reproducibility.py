from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data/operations/mtg_history_foundation/universal_mtg_price_history.csv"
WRITER = ROOT / "scripts/build_universal_mtg_history_foundation.py"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_history_foundation_reproducibility"
KEY_FIELDS = ["canonical_product_id", "observation_date", "source_name", "source_file", "market_price"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(str(row.get(field, "") or "").strip() for field in KEY_FIELDS)


def classify_source(path: str, price_field: str, observation_date: str) -> tuple[str, list[str]]:
    lower = path.lower().replace("\\", "/")
    reasons: list[str] = []
    if "secret_lair" in lower:
        reasons.append("SECRET_LAIR_SOURCE")
    if price_field in {"evaluated_market_value_usd", "market_value_usd"}:
        reasons.append("DERIVED_VALUATION_FIELD")
    if any(token in lower for token in ("current", "latest", "snapshot")):
        reasons.append("CURRENT_OR_SNAPSHOT_SOURCE")
    if not observation_date:
        reasons.append("MISSING_OBSERVATION_DATE")
    return ("SEMANTIC_REVIEW_REQUIRED" if reasons else "RAW_CANDIDATE"), reasons


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["source_file"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [str(p) for p in (TARGET, WRITER) if not p.is_file()]
    if missing:
        print(json.dumps({"status": "FAIL_REQUIRED_INPUTS_MISSING", "missing": missing}, indent=2))
        return 1 if args.strict else 0

    target_hash_before = sha256(TARGET)
    with tempfile.TemporaryDirectory(prefix="collector-history-rebuild-") as temp_dir:
        rebuild_root = Path(temp_dir)
        completed = subprocess.run(
            [sys.executable, str(WRITER), "--output-root", str(rebuild_root)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        rebuilt = rebuild_root / "universal_mtg_price_history.csv"
        if completed.returncode != 0 or not rebuilt.is_file():
            summary = {
                "status": "FAIL_REBUILD_EXECUTION",
                "writer_exit_code": completed.returncode,
                "stdout_tail": completed.stdout[-4000:],
                "stderr_tail": completed.stderr[-4000:],
            }
            (OUT / "collector_history_foundation_reproducibility_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(summary, indent=2))
            return 1 if args.strict else 0

        target_rows = read_rows(TARGET)
        rebuilt_rows = read_rows(rebuilt)
        target_keys = Counter(key(row) for row in target_rows)
        rebuilt_keys = Counter(key(row) for row in rebuilt_rows)
        missing_keys = list((target_keys - rebuilt_keys).elements())
        extra_keys = list((rebuilt_keys - target_keys).elements())

        source_stats: dict[str, dict[str, object]] = {}
        for row in rebuilt_rows:
            source_file = str(row.get("source_file", "") or "")
            state, reasons = classify_source(source_file, str(row.get("price_field", "") or ""), str(row.get("observation_date", "") or ""))
            item = source_stats.setdefault(source_file, {
                "source_file": source_file,
                "row_count": 0,
                "product_count": set(),
                "first_observation_date": "",
                "last_observation_date": "",
                "semantic_state": state,
                "semantic_reasons": set(),
            })
            item["row_count"] = int(item["row_count"]) + 1
            cast_products = item["product_count"]
            assert isinstance(cast_products, set)
            cast_products.add(str(row.get("canonical_product_id", "") or ""))
            cast_reasons = item["semantic_reasons"]
            assert isinstance(cast_reasons, set)
            cast_reasons.update(reasons)
            date = str(row.get("observation_date", "") or "")
            if date:
                first = str(item["first_observation_date"] or "")
                last = str(item["last_observation_date"] or "")
                item["first_observation_date"] = date if not first or date < first else first
                item["last_observation_date"] = date if not last or date > last else last

        inventory: list[dict[str, object]] = []
        for item in source_stats.values():
            products = item.pop("product_count")
            reasons = item.pop("semantic_reasons")
            item["distinct_product_count"] = len(products) if isinstance(products, set) else 0
            item["semantic_reasons"] = "|".join(sorted(reasons)) if isinstance(reasons, set) else ""
            inventory.append(item)
        inventory.sort(key=lambda row: (-int(row["row_count"]), str(row["source_file"])))

        mismatch_rows = [
            {"mismatch_type": "MISSING_FROM_REBUILD", **dict(zip(KEY_FIELDS, values))}
            for values in missing_keys[:10000]
        ] + [
            {"mismatch_type": "EXTRA_IN_REBUILD", **dict(zip(KEY_FIELDS, values))}
            for values in extra_keys[:10000]
        ]

        inventory_path = OUT / "collector_history_foundation_contributing_source_inventory.csv"
        mismatch_path = OUT / "collector_history_foundation_reconciliation_mismatches.csv"
        write_csv(inventory_path, inventory)
        write_csv(mismatch_path, mismatch_rows)

        target_hash_after = sha256(TARGET)
        exact_key_reproduction = not missing_keys and not extra_keys and len(target_rows) == len(rebuilt_rows)
        semantically_clean_sources = [row for row in inventory if row["semantic_state"] == "RAW_CANDIDATE"]
        review_sources = [row for row in inventory if row["semantic_state"] != "RAW_CANDIDATE"]
        summary = {
            "block_name": "Collector V1 History Foundation Reproducibility Audit",
            "block_version": "1.0.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "target_path": str(TARGET.relative_to(ROOT)),
            "writer_path": str(WRITER.relative_to(ROOT)),
            "target_sha256_before": target_hash_before,
            "target_sha256_after": target_hash_after,
            "target_not_mutated": target_hash_before == target_hash_after,
            "writer_exit_code": completed.returncode,
            "target_row_count": len(target_rows),
            "rebuilt_row_count": len(rebuilt_rows),
            "missing_key_count": len(missing_keys),
            "extra_key_count": len(extra_keys),
            "exact_key_reproduction": exact_key_reproduction,
            "contributing_source_count": len(inventory),
            "raw_candidate_source_count": len(semantically_clean_sources),
            "semantic_review_source_count": len(review_sources),
            "inventory_path": str(inventory_path.relative_to(ROOT)),
            "inventory_sha256": sha256(inventory_path),
            "mismatch_path": str(mismatch_path.relative_to(ROOT)),
            "mismatch_sha256": sha256(mismatch_path),
            "raw_historical_price_authority_certified": False,
            "historical_coverage_assessment_authorized": exact_key_reproduction and not review_sources,
            "lifecycle_panel_build_authorized": False,
            "model_tournament_authorized": False,
            "purchase_recommendations_authorized": False,
            "status": "PASS_COLLECTOR_V1_HISTORY_FOUNDATION_REPRODUCIBILITY_AUDIT",
        }
        (OUT / "collector_history_foundation_reproducibility_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
