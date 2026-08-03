from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_canonical_identity_lineage_recertification_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_canonical_identity_lineage_recertification/collector_authority_schema_preflight.json"
ID_CANDIDATES = ["canonical_product_id", "product_id", "asset_id"]
TCG_CANDIDATES = ["tcgplayer_product_id", "resolved_tcgplayer_product_id"]
NAME_CANDIDATES = ["product_name", "canonical_product_name", "name", "asset_name"]


def first_present(fields: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in fields:
            return candidate
    return None


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []
    failures: list[str] = []

    for authority, relative in contract["authorities"].items():
        path = ROOT / relative
        record: dict[str, object] = {
            "authority": authority,
            "path": relative,
            "exists": path.is_file(),
            "fields": [],
            "row_count": 0,
            "canonical_id_field": None,
            "tcgplayer_id_field": None,
            "product_name_field": None,
            "target_id_field": None,
            "target_name_field": None,
            "member_id_field": None,
            "member_name_field": None,
            "identity_mode": None,
        }
        if not path.is_file():
            failures.append(f"MISSING_AUTHORITY:{authority}")
            results.append(record)
            continue

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            row_count = sum(1 for _ in reader)

        canonical_field = first_present(fields, ID_CANDIDATES)
        tcg_field = first_present(fields, TCG_CANDIDATES)
        name_field = first_present(fields, NAME_CANDIDATES)
        target_id = first_present(fields, ["target_canonical_product_id"])
        target_name = first_present(fields, ["target_product_name"])
        member_id = first_present(fields, ["comparable_canonical_product_id", "member_canonical_product_id"])
        member_name = first_present(fields, ["comparable_product_name", "member_product_name"])

        if target_id and target_name and member_id and member_name:
            identity_mode = "TARGET_MEMBER_CANONICAL_ID_PLUS_NAME"
        elif canonical_field and name_field:
            identity_mode = "CANONICAL_ID_PLUS_NAME"
        elif canonical_field:
            identity_mode = "CANONICAL_ID_ONLY"
        elif tcg_field and name_field:
            identity_mode = "TCGPLAYER_ID_PLUS_NAME"
        elif tcg_field:
            identity_mode = "TCGPLAYER_ID_ONLY"
        else:
            identity_mode = "NO_RECOGNIZED_IDENTITY_FIELDS"
            failures.append(f"NO_RECOGNIZED_IDENTITY_FIELDS:{authority}")

        record.update(
            {
                "fields": fields,
                "row_count": row_count,
                "canonical_id_field": canonical_field,
                "tcgplayer_id_field": tcg_field,
                "product_name_field": name_field,
                "target_id_field": target_id,
                "target_name_field": target_name,
                "member_id_field": member_id,
                "member_name_field": member_name,
                "identity_mode": identity_mode,
            }
        )
        results.append(record)

    summary = {
        "contract": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
        "authority_count": len(results),
        "failures": failures,
        "authorities": results,
        "status": "PASS_COLLECTOR_AUTHORITY_SCHEMA_PREFLIGHT" if not failures else "FAIL_COLLECTOR_AUTHORITY_SCHEMA_PREFLIGHT",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n============================================================")
    print("COLLECTOR AUTHORITY SCHEMA PREFLIGHT")
    print("============================================================")
    for row in results:
        print(f"\nAuthority: {row['authority']}")
        print(f"Path: {row['path']}")
        print(f"Rows: {row['row_count']}")
        print(f"Identity mode: {row['identity_mode']}")
        print(f"Canonical ID field: {row['canonical_id_field']}")
        print(f"TCGplayer ID field: {row['tcgplayer_id_field']}")
        print(f"Product name field: {row['product_name_field']}")
        print(f"Target ID field: {row['target_id_field']}")
        print(f"Target name field: {row['target_name_field']}")
        print(f"Member ID field: {row['member_id_field']}")
        print(f"Member name field: {row['member_name_field']}")
        print("Fields: " + ", ".join(row["fields"]))
    print("\nStatus: " + summary["status"])
    if failures:
        print("Failures:")
        for failure in failures:
            print("  " + failure)
    print("No model execution, output invalidation, calibration, ranking, or purchasing occurred.")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
