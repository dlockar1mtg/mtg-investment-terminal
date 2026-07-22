from __future__ import annotations

import sqlite3
from pathlib import Path

from terminal2.market_sources.ebay_universe import (
    build_complete_universe,
    load_operational_collector_products,
)


def make_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE products (
                investment_product_id TEXT PRIMARY KEY,
                set_name TEXT,
                box_name TEXT,
                tcgplayer_product_id TEXT,
                product_type TEXT,
                approval_status TEXT,
                release_date TEXT,
                language TEXT
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "MTG-COLLECTOR-1",
                    "Modern Horizons 3",
                    "Modern Horizons 3 Collector Booster Box",
                    "123",
                    "Collector Booster Display",
                    "approved",
                    "2024-06-14",
                    "English",
                ),
                (
                    "MTG-PLAY-1",
                    "Modern Horizons 3",
                    "Modern Horizons 3 Play Booster Box",
                    "124",
                    "Play Booster Display",
                    "approved",
                    "2024-06-14",
                    "English",
                ),
                (
                    "MTG-COLLECTOR-JP",
                    "Example Set",
                    "Example Set Collector Booster Box",
                    "125",
                    "Collector Booster Display",
                    "approved",
                    "2024-01-01",
                    "Japanese",
                ),
                (
                    "MTG-COLLECTOR-JP-NAME",
                    "FINAL FANTASY",
                    "FINAL FANTASY Collector Booster Display (Japanese)",
                    "127",
                    "Collector Booster Display",
                    "approved",
                    "2025-06-13",
                    "",
                ),
                (
                    "MTG-COLLECTOR-PENDING",
                    "Pending Set",
                    "Pending Set Collector Booster Box",
                    "126",
                    "Collector Booster Display",
                    "pending",
                    "2024-01-01",
                    "English",
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_operational_lane_loads_only_approved_english_collectors(tmp_path):
    db = tmp_path / "terminal.sqlite"
    make_db(db)

    products = load_operational_collector_products(db)

    assert len(products) == 1
    assert products[0].canonical_product_id == "MTG-COLLECTOR-1"
    assert products[0].product_class == "COLLECTOR_BOOSTER_BOX"
    assert "Collector Booster Box" in products[0].ebay_query


def test_complete_universe_adds_operational_collector_lane(tmp_path):
    db = tmp_path / "terminal.sqlite"
    make_db(db)

    universe = build_complete_universe(db)

    assert any(
        product.canonical_product_id == "MTG-COLLECTOR-1"
        and product.product_class == "COLLECTOR_BOOSTER_BOX"
        for product in universe
    )
    names = "\n".join(product.canonical_product_name.lower() for product in universe)
    assert "play booster box" not in names
    assert "(japanese)" not in names
