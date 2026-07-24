from __future__ import annotations

from pathlib import Path
import sqlite3

import terminal2.forecast.exports as exports_module
from terminal2.db.schema import init_db


def _ensure_market_intelligence_table(
    database_path: Path,
) -> None:
    connection = sqlite3.connect(database_path)

    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_intelligence (
                investment_product_id TEXT PRIMARY KEY,
                market_intelligence_score REAL,
                market_intelligence_confidence REAL,
                supply_signal_score REAL,
                sales_velocity_score REAL,
                liquidity_score REAL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def _seed_database(database_path: Path) -> None:
    init_db(database_path)
    _ensure_market_intelligence_table(database_path)

    connection = sqlite3.connect(database_path)

    try:
        connection.executemany(
            """
            INSERT INTO products (
                investment_product_id,
                box_name,
                product_type,
                approval_status
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    "PRICED-001",
                    "Priced Product",
                    "Collector Booster Display",
                    "approved",
                ),
                (
                    "UNPRICED-001",
                    "Unpriced Product",
                    "Collector Booster Display",
                    "approved",
                ),
                (
                    "ZERO-001",
                    "Zero Price Product",
                    "Collector Booster Display",
                    "approved",
                ),
                (
                    "UNAPPROVED-001",
                    "Unapproved Product",
                    "Collector Booster Display",
                    "pending",
                ),
            ],
        )

        connection.executemany(
            """
            INSERT INTO investment_scores (
                investment_product_id,
                current_price,
                investment_score,
                risk_adjusted_score,
                rating,
                buy_signal,
                expected_cagr,
                projection_confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "PRICED-001",
                    250.0,
                    50.0,
                    47.5,
                    "Avoid",
                    "Wait",
                    0.08,
                    8.3,
                ),
                (
                    "ZERO-001",
                    0.0,
                    50.0,
                    47.5,
                    "Avoid",
                    "Wait",
                    0.08,
                    0.0,
                ),
                (
                    "UNAPPROVED-001",
                    300.0,
                    50.0,
                    47.5,
                    "Avoid",
                    "Wait",
                    0.08,
                    8.3,
                ),
            ],
        )

        connection.commit()
    finally:
        connection.close()


def test_forecast_universe_contains_only_approved_positive_prices(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    _seed_database(database_path)

    monkeypatch.setattr(
        exports_module,
        "migrate_module2",
        lambda: None,
    )
    monkeypatch.setattr(
        exports_module,
        "get_connection",
        lambda: sqlite3.connect(database_path),
    )

    result = exports_module.load_forecast_universe()

    assert len(result) == 1
    assert result.iloc[0]["investment_product_id"] == (
        "PRICED-001"
    )
    assert result.iloc[0]["current_price"] == 250.0


def test_forecast_universe_is_empty_without_eligible_scores(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    init_db(database_path)
    _ensure_market_intelligence_table(database_path)

    connection = sqlite3.connect(database_path)

    try:
        connection.execute(
            """
            INSERT INTO products (
                investment_product_id,
                box_name,
                product_type,
                approval_status
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "UNPRICED-001",
                "Unpriced Product",
                "Collector Booster Display",
                "approved",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(
        exports_module,
        "migrate_module2",
        lambda: None,
    )
    monkeypatch.setattr(
        exports_module,
        "get_connection",
        lambda: sqlite3.connect(database_path),
    )

    result = exports_module.load_forecast_universe()

    assert result.empty