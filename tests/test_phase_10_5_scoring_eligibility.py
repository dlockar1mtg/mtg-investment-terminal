from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd

import terminal2.analytics.scoring as scoring_module
from terminal2.db.schema import init_db


def _seed_database(database_path: Path) -> None:
    init_db(database_path)

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
                    "Priced Collector Booster Display",
                    "Collector Booster Display",
                    "approved",
                ),
                (
                    "UNPRICED-001",
                    "Unpriced Collector Booster Display",
                    "Collector Booster Display",
                    "approved",
                ),
            ],
        )

        connection.execute(
            """
            INSERT INTO product_features (
                investment_product_id,
                latest_price,
                observation_count,
                trend_score,
                volatility_score,
                history_confidence
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "PRICED-001",
                250.0,
                1,
                50.0,
                50.0,
                8.3,
            ),
        )

        connection.execute(
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
            (
                "UNPRICED-001",
                0.0,
                50.0,
                47.5,
                "Avoid",
                "Wait",
                0.12,
                0.0,
            ),
        )

        connection.commit()
    finally:
        connection.close()


def test_scoring_excludes_unpriced_products(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    _seed_database(database_path)

    monkeypatch.setattr(
        scoring_module,
        "init_db",
        lambda: init_db(database_path),
    )
    monkeypatch.setattr(
        scoring_module,
        "get_connection",
        lambda: sqlite3.connect(database_path),
    )

    result = scoring_module.score_from_features()

    assert len(result) == 1
    assert result.iloc[0]["investment_product_id"] == (
        "PRICED-001"
    )
    assert result.iloc[0]["latest_price"] == 250.0

    connection = sqlite3.connect(database_path)

    try:
        rows = connection.execute(
            """
            SELECT
                investment_product_id,
                current_price
            FROM investment_scores
            ORDER BY investment_product_id
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [("PRICED-001", 250.0)]


def test_scoring_clears_scores_when_no_prices_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    init_db(database_path)

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

        connection.execute(
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
            (
                "UNPRICED-001",
                0.0,
                50.0,
                47.5,
                "Avoid",
                "Wait",
                0.12,
                0.0,
            ),
        )

        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(
        scoring_module,
        "init_db",
        lambda: init_db(database_path),
    )
    monkeypatch.setattr(
        scoring_module,
        "get_connection",
        lambda: sqlite3.connect(database_path),
    )

    result = scoring_module.score_from_features()

    assert isinstance(result, pd.DataFrame)
    assert result.empty

    connection = sqlite3.connect(database_path)

    try:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM investment_scores
            """
        ).fetchone()[0]
    finally:
        connection.close()

    assert count == 0