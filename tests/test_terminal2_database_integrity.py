from __future__ import annotations

import sqlite3
from pathlib import Path

from terminal2.db.module1_migration import PRODUCT_COLUMNS
from terminal2.db.module2_migration import migrate_module2


REQUIRED_TABLES = {
    "products",
    "price_observations",
    "source_runs",
    "product_features",
    "investment_scores",
    "product_metadata",
    "supply_observations",
    "sales_observations",
    "market_intelligence",
    "market_health_history",
    "source_health_history",
}


REQUIRED_INDEXES = {
    "idx_price_obs_product_date",
    "idx_price_obs_date",
    "idx_products_type",
    "idx_supply_product_date",
    "idx_sales_product_date",
    "idx_market_intelligence_score",
}


def database_objects(
    connection: sqlite3.Connection,
    object_type: str,
) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = ?
          AND name NOT LIKE 'sqlite_%'
        """,
        (object_type,),
    ).fetchall()

    return {row[0] for row in rows}


def test_module2_migration_isolated_and_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal2-certification.sqlite"

    migrate_module2(database_path)
    migrate_module2(database_path)

    assert database_path.exists()
    assert database_path.stat().st_size > 0

    connection = sqlite3.connect(database_path)

    try:
        tables = database_objects(connection, "table")
        indexes = database_objects(connection, "index")

        assert REQUIRED_TABLES <= tables
        assert REQUIRED_INDEXES <= indexes

        product_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(products)"
            )
        }

        assert set(PRODUCT_COLUMNS) <= product_columns

        integrity_result = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        assert integrity_result == "ok"
        assert foreign_key_violations == []

    finally:
        connection.close()


def test_foreign_key_contract_is_enforced_when_enabled(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "foreign-key-test.sqlite"
    migrate_module2(database_path)

    connection = sqlite3.connect(database_path)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        try:
            connection.execute(
                """
                INSERT INTO price_observations (
                    observation_date,
                    investment_product_id,
                    price_source
                )
                VALUES (?, ?, ?)
                """,
                (
                    "2026-07-21",
                    "missing-product",
                    "certification",
                ),
            )

        except sqlite3.IntegrityError:
            pass

        else:
            raise AssertionError(
                "Expected foreign-key enforcement failure."
            )

    finally:
        connection.close()