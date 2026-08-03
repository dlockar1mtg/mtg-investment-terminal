from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_current_supply_snapshot_resolution_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_current_supply_snapshot_resolution"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_present(fieldnames: list[str], aliases: list[str]) -> str:
    lowered = {name.strip().lower(): name for name in fieldnames}
    for alias in aliases:
        if alias.lower() in lowered:
            return lowered[alias.lower()]
    return ""


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    candidates: list[dict[str, Any]] = []
    canonical_path = ROOT / contract["canonical_output_path"]

    roots = [ROOT / value for value in contract["bounded_search_roots"]]
    for search_root in roots:
        if not search_root.is_dir():
            continue
        for path in search_root.rglob("*.csv"):
            if path.resolve() == canonical_path.resolve():
                continue
            try:
                rows = read_csv(path)
            except Exception:
                continue
            if not rows:
                continue
            fields = list(rows[0].keys())
            identity_field = first_present(fields, contract["required_identity_aliases"])
            feature_fields = {
                key: first_present(fields, aliases)
                for key, aliases in contract["overlay_feature_alias_groups"].items()
            }
            if not identity_field:
                continue
            identities = [str(row.get(identity_field, "")).strip() for row in rows]
            nonblank_identities = [value for value in identities if value]
            identity_coverage = len(nonblank_identities) / max(len(rows), 1)
            populated_features = 0
            total_feature_cells = len(rows) * len(feature_fields)
            for row in rows:
                for field in feature_fields.values():
                    if field and str(row.get(field, "")).strip():
                        populated_features += 1
            feature_coverage = populated_features / max(total_feature_cells, 1)
            row_count_score = 1.0 if len(rows) == contract["required_product_rows"] else 0.0
            schema_group_count = sum(bool(value) for value in feature_fields.values())
            valid = (
                len(rows) == contract["required_product_rows"]
                and identity_coverage >= contract["minimum_identity_coverage"]
                and feature_coverage >= contract["minimum_overlay_feature_coverage"]
                and schema_group_count >= 3
            )
            candidates.append({
                "source_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "row_count": len(rows),
                "identity_field": identity_field,
                "identity_coverage": round(identity_coverage, 6),
                "overlay_feature_groups_present": schema_group_count,
                "overlay_feature_coverage": round(feature_coverage, 6),
                "row_count_score": row_count_score,
                "source_sha256": sha256(path),
                "valid_supply_candidate": valid,
            })

    candidates.sort(
        key=lambda row: (
            bool(row["valid_supply_candidate"]),
            float(row["row_count_score"]),
            float(row["identity_coverage"]),
            int(row["overlay_feature_groups_present"]),
            float(row["overlay_feature_coverage"]),
            row["source_path"],
        ),
        reverse=True,
    )
    valid = [row for row in candidates if row["valid_supply_candidate"]]
    if not valid:
        failures.append("NO_VALID_50_PRODUCT_SUPPLY_SNAPSHOT_FOUND")
    elif len(valid) > 1:
        top = valid[0]
        tied = [row for row in valid if (
            row["row_count_score"],
            row["identity_coverage"],
            row["overlay_feature_groups_present"],
            row["overlay_feature_coverage"],
        ) == (
            top["row_count_score"],
            top["identity_coverage"],
            top["overlay_feature_groups_present"],
            top["overlay_feature_coverage"],
        )]
        if len(tied) > 1:
            failures.append("AMBIGUOUS_TOP_SUPPLY_SNAPSHOT_CANDIDATES")

    selected = valid[0] if valid and not failures else None
    source_path: Path | None = ROOT / selected["source_path"] if selected else None
    if source_path:
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, canonical_path)
        if sha256(source_path) != sha256(canonical_path):
            failures.append("CANONICAL_COPY_HASH_MISMATCH")
        if len(read_csv(canonical_path)) != contract["required_product_rows"]:
            failures.append("CANONICAL_COPY_ROW_COUNT_MISMATCH")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT / "collector_current_supply_snapshot_candidate_registry.csv", candidates)
    selection_rows = []
    if selected and source_path:
        selection_rows.append({
            **selected,
            "canonical_output_path": contract["canonical_output_path"],
            "canonical_sha256": sha256(canonical_path),
            "source_modified": False,
            "historical_backtest_use_allowed": False,
            "point_forecast_rewrite_allowed": False,
            "purchase_recommendations_authorized": False,
        })
    write_csv(OUTPUT / "collector_current_supply_snapshot_selection.csv", selection_rows)

    status = contract["expected_status"] if not failures else "FAIL_COLLECTOR_CURRENT_SUPPLY_SNAPSHOT_RESOLUTION"
    summary = {
        "block_name": contract["contract_name"],
        "block_version": contract["contract_version"],
        "snapshot_id": contract["snapshot_id"],
        "bounded_search_roots": contract["bounded_search_roots"],
        "csv_candidates_evaluated": len(candidates),
        "valid_supply_candidates": len(valid),
        "selected_source_path": selected["source_path"] if selected else "",
        "canonical_output_path": contract["canonical_output_path"] if selected else "",
        "selected_row_count": selected["row_count"] if selected else 0,
        "selected_identity_coverage": selected["identity_coverage"] if selected else 0.0,
        "selected_overlay_feature_coverage": selected["overlay_feature_coverage"] if selected else 0.0,
        "source_modified": False,
        "canonical_copy_created": bool(selected and canonical_path.is_file()),
        "historical_backtest_use_allowed": False,
        "point_forecast_rewrite_allowed": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": status,
    }
    (OUTPUT / "collector_current_supply_snapshot_resolution_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
