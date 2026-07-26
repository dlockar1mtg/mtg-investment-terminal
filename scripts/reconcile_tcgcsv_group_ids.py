from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

REQUIRED_MAP_COLUMNS = {
    "box_name",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
}
ID_COLUMNS = ("tcgplayer_product_id", "approved_tcgplayer_product_id")
GROUP_COLUMNS = ("tcgcsv_group_id", "tcgcsv_group_id_master")
CATEGORY_COLUMNS = ("tcgcsv_category_id", "tcgcsv_category_id_master")
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", "node_modules", "operations"}


def _clean(value: object) -> str:
    return str(value or "").strip().strip('"')


def _first(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = _clean(row.get(name))
        if value:
            return value
    return ""


def _eligible(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".csv" and not any(part in SKIP_PARTS for part in path.parts)


def reconcile(product_map: Path, search_root: Path) -> dict[str, object]:
    with product_map.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        rows = list(reader)

    missing_columns = sorted(REQUIRED_MAP_COLUMNS - columns)
    targets = {
        _clean(row.get("tcgplayer_product_id")): {
            "box_name": _clean(row.get("box_name")),
            "tcgplayer_product_id": _clean(row.get("tcgplayer_product_id")),
            "current_group_id": _clean(row.get("tcgcsv_group_id")),
        }
        for row in rows
        if _clean(row.get("tcgplayer_product_id"))
    }

    evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
    files_scanned = 0
    rows_scanned = 0
    for path in search_root.rglob("*.csv"):
        relative = path.relative_to(search_root)
        if not _eligible(relative) or path.resolve() == product_map.resolve():
            continue
        files_scanned += 1
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = set(reader.fieldnames or [])
                if not fieldnames.intersection(ID_COLUMNS) or not fieldnames.intersection(GROUP_COLUMNS):
                    continue
                for row in reader:
                    rows_scanned += 1
                    product_id = _first(row, ID_COLUMNS)
                    group_id = _first(row, GROUP_COLUMNS)
                    if product_id not in targets or not group_id:
                        continue
                    evidence[product_id].append(
                        {
                            "tcgcsv_group_id": group_id,
                            "tcgcsv_category_id": _first(row, CATEGORY_COLUMNS),
                            "source_file": relative.as_posix(),
                        }
                    )
        except (OSError, csv.Error, UnicodeError):
            continue

    results: list[dict[str, object]] = []
    resolved = 0
    ambiguous = 0
    unresolved = 0
    for product_id, target in targets.items():
        observations = evidence.get(product_id, [])
        group_ids = sorted({item["tcgcsv_group_id"] for item in observations})
        if target["current_group_id"]:
            status = "ALREADY_MAPPED"
            selected = target["current_group_id"]
            resolved += 1
        elif len(group_ids) == 1:
            status = "RESOLVED"
            selected = group_ids[0]
            resolved += 1
        elif len(group_ids) > 1:
            status = "AMBIGUOUS"
            selected = ""
            ambiguous += 1
        else:
            status = "UNRESOLVED"
            selected = ""
            unresolved += 1
        results.append(
            {
                **target,
                "status": status,
                "selected_group_id": selected,
                "observed_group_ids": group_ids,
                "evidence": observations,
            }
        )

    if missing_columns:
        status = "FAILED"
        reasons = ["TCGCSV_PRODUCT_MAP_COLUMNS_MISSING"]
    elif ambiguous:
        status = "INCOMPLETE"
        reasons = ["TCGCSV_GROUP_ID_AMBIGUITY_REQUIRES_REVIEW"]
    elif unresolved:
        status = "INCOMPLETE"
        reasons = ["TCGCSV_GROUP_IDS_NOT_FULLY_RESOLVED"]
    else:
        status = "PASS"
        reasons = ["TCGCSV_GROUP_IDS_RESOLVED_FROM_LOCAL_EVIDENCE"]

    return {
        "status": status,
        "product_map": str(product_map.resolve()),
        "search_root": str(search_root.resolve()),
        "files_scanned": files_scanned,
        "rows_scanned": rows_scanned,
        "target_products": len(targets),
        "resolved_products": resolved,
        "ambiguous_products": ambiguous,
        "unresolved_products": unresolved,
        "missing_required_columns": missing_columns,
        "results": results,
        "reason_codes": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve TCGCSV group IDs from local repository CSV evidence")
    parser.add_argument("--product-map", type=Path, required=True)
    parser.add_argument("--search-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("data/operations/tcgcsv/group_id_reconciliation.json"))
    args = parser.parse_args()

    if not args.product_map.is_file():
        payload = {"status": "FAILED", "reason_codes": ["TCGCSV_PRODUCT_MAP_NOT_AVAILABLE"]}
        exit_code = 1
    elif not args.search_root.is_dir():
        payload = {"status": "FAILED", "reason_codes": ["TCGCSV_SEARCH_ROOT_NOT_AVAILABLE"]}
        exit_code = 1
    else:
        payload = reconcile(args.product_map, args.search_root)
        exit_code = 0 if payload["status"] == "PASS" else 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
