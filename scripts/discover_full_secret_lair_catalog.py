from __future__ import annotations

import csv
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.config import DB_FILE
VALIDATION_ROOT = ROOT / "data/validation/phase_10/premium_universe_eligibility"
CURRENT_SOURCE = VALIDATION_ROOT / "secret_lair_structural_candidates_2026-07-22.csv"
DISCOVERY_OUTPUT = VALIDATION_ROOT / "secret_lair_full_catalog_discovery.csv"
MISSING_OUTPUT = VALIDATION_ROOT / "secret_lair_catalog_missing_from_candidates.csv"
SUMMARY_OUTPUT = VALIDATION_ROOT / "secret_lair_catalog_discovery_summary.csv"

SECRET_LAIR_TERMS = (
    "secret lair",
    "secretlair",
    "secret lair drop",
    "secret lair x",
)


def clean(value: object) -> str:
    return str(value or "").strip()


def norm(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", clean(value).lower())
    return " ".join(text.split())


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first_existing(columns: set[str], *names: str) -> str | None:
    for name in names:
        if name in columns:
            return name
    return None


def sql_expr(column: str | None, alias: str) -> str:
    return f'"{column}" AS "{alias}"' if column else f"'' AS \"{alias}\""


def identify_finish(name: str) -> str:
    value = norm(name)
    if "rainbow foil" in value:
        return "rainbow_foil"
    if "etched foil" in value:
        return "etched_foil"
    if "galaxy foil" in value:
        return "galaxy_foil"
    if "traditional foil" in value or "foil edition" in value or value.endswith(" foil"):
        return "traditional_foil"
    if "non foil" in value or "nonfoil" in value:
        return "non_foil"
    return "unspecified"


def identify_packaging(name: str, product_type: str) -> str:
    value = norm(f"{name} {product_type}")
    if "commander deck" in value or "deck" in value:
        return "deck"
    if "bundle" in value:
        return "bundle"
    if "countdown kit" in value or "kit" in value:
        return "kit"
    return "individual_drop"


def main() -> None:
    db_path = Path(DB_FILE)
    if not db_path.exists():
        raise FileNotFoundError(f"Operational database not found: {db_path}")

    current_rows = read_csv(CURRENT_SOURCE)
    current_ids = {
        clean(row.get("tcgplayer_product_id"))
        for row in current_rows
        if clean(row.get("tcgplayer_product_id"))
    }
    current_names = {
        norm(row.get("canonical_product_name"))
        for row in current_rows
        if norm(row.get("canonical_product_name"))
    }

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "products" not in table_names:
            raise RuntimeError("Required products table was not found")

        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(products)").fetchall()
        }

        id_col = first_existing(columns, "investment_product_id", "canonical_product_id", "product_id", "id")
        tcg_col = first_existing(columns, "tcgplayer_product_id", "tcgplayer_id")
        set_col = first_existing(columns, "set_name", "canonical_set_name", "product_line")
        name_col = first_existing(columns, "box_name", "product_name", "canonical_product_name", "name")
        type_col = first_existing(columns, "product_type", "canonical_product_type", "type")
        family_col = first_existing(columns, "product_family", "canonical_product_family", "family")
        approval_col = first_existing(columns, "approval_status", "investment_approval_status", "status")
        language_col = first_existing(columns, "language")
        release_col = first_existing(columns, "release_date", "set_release_date")

        query = f"""
            SELECT
                {sql_expr(id_col, 'source_product_id')},
                {sql_expr(tcg_col, 'tcgplayer_product_id')},
                {sql_expr(set_col, 'set_name')},
                {sql_expr(name_col, 'product_name')},
                {sql_expr(type_col, 'product_type')},
                {sql_expr(family_col, 'product_family')},
                {sql_expr(approval_col, 'approval_status')},
                {sql_expr(language_col, 'language')},
                {sql_expr(release_col, 'release_date')}
            FROM products
        """
        raw_rows = connection.execute(query).fetchall()
    finally:
        connection.close()

    discovered: list[dict[str, object]] = []
    for row in raw_rows:
        combined = norm(
            " ".join(
                clean(row[key])
                for key in (
                    "set_name",
                    "product_name",
                    "product_type",
                    "product_family",
                )
            )
        )
        if not any(term in combined for term in SECRET_LAIR_TERMS):
            continue

        product_name = clean(row["product_name"]) or clean(row["set_name"])
        tcgplayer_id = clean(row["tcgplayer_product_id"])
        normalized_name = norm(product_name)
        in_candidates_by_id = bool(tcgplayer_id and tcgplayer_id in current_ids)
        in_candidates_by_name = normalized_name in current_names
        candidate_status = (
            "IN_CURRENT_CANDIDATES"
            if in_candidates_by_id or in_candidates_by_name
            else "MISSING_FROM_CURRENT_CANDIDATES"
        )

        discovered.append(
            {
                "source_product_id": clean(row["source_product_id"]),
                "tcgplayer_product_id": tcgplayer_id,
                "set_name": clean(row["set_name"]),
                "product_name": product_name,
                "normalized_product_name": normalized_name,
                "product_type": clean(row["product_type"]),
                "product_family": clean(row["product_family"]),
                "approval_status": clean(row["approval_status"]),
                "language": clean(row["language"]),
                "release_date": clean(row["release_date"]),
                "finish": identify_finish(product_name),
                "packaging_level": identify_packaging(product_name, clean(row["product_type"])),
                "candidate_status": candidate_status,
                "matched_by_id": in_candidates_by_id,
                "matched_by_name": in_candidates_by_name,
            }
        )

    deduped: dict[tuple[str, str], dict[str, object]] = {}
    for row in discovered:
        key = (
            clean(row["tcgplayer_product_id"]),
            clean(row["normalized_product_name"]),
        )
        deduped.setdefault(key, row)

    final_rows = sorted(
        deduped.values(),
        key=lambda row: (
            clean(row["packaging_level"]),
            clean(row["product_name"]),
            clean(row["finish"]),
        ),
    )
    missing_rows = [
        row for row in final_rows
        if row["candidate_status"] == "MISSING_FROM_CURRENT_CANDIDATES"
    ]

    fields = [
        "source_product_id",
        "tcgplayer_product_id",
        "set_name",
        "product_name",
        "normalized_product_name",
        "product_type",
        "product_family",
        "approval_status",
        "language",
        "release_date",
        "finish",
        "packaging_level",
        "candidate_status",
        "matched_by_id",
        "matched_by_name",
    ]
    write_csv(DISCOVERY_OUTPUT, final_rows, fields)
    write_csv(MISSING_OUTPUT, missing_rows, fields)

    summary_rows: list[dict[str, object]] = [
        {"metric": "current_candidate_rows", "value": len(current_rows)},
        {"metric": "operational_secret_lair_rows", "value": len(final_rows)},
        {"metric": "missing_from_current_candidates", "value": len(missing_rows)},
    ]
    for packaging in sorted({clean(row["packaging_level"]) for row in final_rows}):
        summary_rows.append(
            {
                "metric": f"packaging_{packaging}",
                "value": sum(1 for row in final_rows if row["packaging_level"] == packaging),
            }
        )
    for finish in sorted({clean(row["finish"]) for row in final_rows}):
        summary_rows.append(
            {
                "metric": f"finish_{finish}",
                "value": sum(1 for row in final_rows if row["finish"] == finish),
            }
        )
    write_csv(SUMMARY_OUTPUT, summary_rows, ["metric", "value"])

    print("SECRET LAIR FULL CATALOG DISCOVERY: COMPLETE")
    print(f"Database: {db_path}")
    print(f"Current candidate rows: {len(current_rows)}")
    print(f"Operational Secret Lair rows: {len(final_rows)}")
    print(f"Missing from current candidates: {len(missing_rows)}")
    print(f"Discovery: {DISCOVERY_OUTPUT.relative_to(ROOT)}")
    print(f"Missing: {MISSING_OUTPUT.relative_to(ROOT)}")
    print(f"Summary: {SUMMARY_OUTPUT.relative_to(ROOT)}")
    print("Active eBay universe source was not changed.")


if __name__ == "__main__":
    main()
