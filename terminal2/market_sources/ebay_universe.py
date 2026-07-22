from __future__ import annotations

import sqlite3
from pathlib import Path

from terminal2.config import DB_FILE
from terminal2.market_sources import ebay_matching as base


ORIGINAL_CSV_UNIVERSE = base.build_universe
NON_ENGLISH_NAME_TERMS = (
    " japanese ",
    " german ",
    " french ",
    " italian ",
    " spanish ",
    " portuguese ",
    " korean ",
    " chinese ",
    " russian ",
    " jp ",
    " jpn ",
)


def _normal_key(value: str) -> str:
    return " ".join(base._norm(value).split())


def _name_identifies_non_english(value: str) -> bool:
    normalized = base._norm(value)
    return any(term in normalized for term in NON_ENGLISH_NAME_TERMS)


def load_operational_collector_products(
    db_file: Path = DB_FILE,
) -> list[base.CanonicalProduct]:
    """Load approved English Collector Booster displays from Terminal 2 SQLite."""
    path = Path(db_file)
    if not path.exists():
        return []

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()
        if table is None:
            return []

        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(products)").fetchall()
        }
        required = {
            "investment_product_id",
            "set_name",
            "box_name",
            "tcgplayer_product_id",
            "product_type",
            "approval_status",
        }
        if not required <= columns:
            return []

        release_expression = "release_date" if "release_date" in columns else "''"
        language_expression = "language" if "language" in columns else "''"
        rows = connection.execute(
            f"""
            SELECT
                investment_product_id,
                set_name,
                box_name,
                tcgplayer_product_id,
                product_type,
                approval_status,
                {release_expression} AS release_date,
                {language_expression} AS language
            FROM products
            """
        ).fetchall()
    finally:
        connection.close()

    products: list[base.CanonicalProduct] = []
    for row in rows:
        product_type = base._clean(row["product_type"])
        approval = base._clean(row["approval_status"]).lower()
        language = base._clean(row["language"]).lower()
        product_type_norm = _normal_key(product_type)

        if approval != "approved":
            continue
        if "collector booster" not in product_type_norm:
            continue
        if language and language not in {"english", "en", "en-us"}:
            continue

        product_id = base._clean(row["investment_product_id"])
        set_name = base._clean(row["set_name"])
        box_name = base._clean(row["box_name"])
        name = box_name or (
            f"{set_name} Collector Booster Box" if set_name else ""
        )
        if not product_id or not name:
            continue
        if _name_identifies_non_english(f"{set_name} {name}"):
            continue

        products.append(
            base.CanonicalProduct(
                canonical_product_id=product_id,
                canonical_product_name=name,
                canonical_set_name=set_name,
                product_class="COLLECTOR_BOOSTER_BOX",
                tcgplayer_product_id=base._clean(row["tcgplayer_product_id"]),
                release_date=base._clean(row["release_date"]),
                ebay_query=base.build_query(name, "COLLECTOR_BOOSTER_BOX"),
            )
        )

    return products


def build_complete_universe(
    db_file: Path = DB_FILE,
) -> list[base.CanonicalProduct]:
    """Combine governed CSV lanes with operational Collector Booster products."""
    products = {
        product.canonical_product_id: product
        for product in ORIGINAL_CSV_UNIVERSE()
    }

    tcgplayer_ids = {
        product.tcgplayer_product_id: product.canonical_product_id
        for product in products.values()
        if product.tcgplayer_product_id
    }
    name_keys = {
        _normal_key(product.canonical_product_name): product.canonical_product_id
        for product in products.values()
    }

    for product in load_operational_collector_products(db_file):
        if product.canonical_product_id in products:
            products[product.canonical_product_id] = product
            continue
        if (
            product.tcgplayer_product_id
            and product.tcgplayer_product_id in tcgplayer_ids
        ):
            continue
        if _normal_key(product.canonical_product_name) in name_keys:
            continue
        products[product.canonical_product_id] = product

    return sorted(
        products.values(),
        key=lambda value: (
            value.product_class,
            value.canonical_product_name,
        ),
    )
