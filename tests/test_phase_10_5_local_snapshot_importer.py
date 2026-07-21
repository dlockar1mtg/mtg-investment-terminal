from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from terminal2.db.local_snapshot_importer import (
    SOURCE_NAME,
    import_local_snapshot,
)
from terminal2.db.schema import init_db


def _seed_product(
    database_path: Path,
    *,
    product_id: str = "TEST-001",
) -> None:
    init_db(database_path)

    connection = sqlite3.connect(database_path)

    try:
        connection.execute(
            """
            INSERT INTO products (
                investment_product_id,
                set_name,
                box_name,
                tcgplayer_product_id,
                product_type,
                approval_status,
                approval_method
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                "Test Set",
                "Test Collector Booster Display",
                "123456",
                "Collector Booster Display",
                "approved",
                "test",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _write_model_input(
    path: Path,
    *,
    product_id: str = "TEST-001",
    price: float = 250.0,
) -> None:
    pd.DataFrame(
        [
            {
                "investment_product_id": product_id,
                "box_name": (
                    "Test Collector Booster Display"
                ),
                "tcgplayer_product_id": "123456",
                "current_price": price,
                "estimated_floor_price": 200.0,
                "price_data_quality": 95,
            }
        ]
    ).to_csv(path, index=False)


def _observation_count(
    database_path: Path,
) -> int:
    connection = sqlite3.connect(database_path)

    try:
        return int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM price_observations
                """
            ).fetchone()[0]
        )
    finally:
        connection.close()


def test_dry_run_does_not_write(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    model_input_path = tmp_path / "model_input.csv"

    _seed_product(database_path)
    _write_model_input(model_input_path)

    result = import_local_snapshot(
        model_input_path=model_input_path,
        database_path=database_path,
        observation_date="2026-07-21",
        dry_run=True,
    )

    assert result.source_rows == 1
    assert result.valid_rows == 1
    assert result.matched_rows == 1
    assert result.inserted_rows == 0
    assert _observation_count(database_path) == 0


def test_write_uses_selected_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    model_input_path = tmp_path / "model_input.csv"

    _seed_product(database_path)
    _write_model_input(model_input_path)

    result = import_local_snapshot(
        model_input_path=model_input_path,
        database_path=database_path,
        observation_date="2026-07-21",
    )

    assert result.inserted_rows == 1
    assert _observation_count(database_path) == 1

    connection = sqlite3.connect(database_path)

    try:
        row = connection.execute(
            """
            SELECT
                observation_date,
                investment_product_id,
                price_source,
                market_price
            FROM price_observations
            """
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        "2026-07-21",
        "TEST-001",
        SOURCE_NAME,
        250.0,
    )


def test_same_snapshot_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    model_input_path = tmp_path / "model_input.csv"

    _seed_product(database_path)
    _write_model_input(model_input_path)

    first = import_local_snapshot(
        model_input_path=model_input_path,
        database_path=database_path,
        observation_date="2026-07-21",
    )
    second = import_local_snapshot(
        model_input_path=model_input_path,
        database_path=database_path,
        observation_date="2026-07-21",
    )

    assert first.inserted_rows == 1
    assert second.inserted_rows == 1
    assert _observation_count(database_path) == 1


def test_unapproved_or_unknown_product_is_rejected(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    model_input_path = tmp_path / "model_input.csv"

    _seed_product(database_path)
    _write_model_input(
        model_input_path,
        product_id="UNKNOWN-001",
    )

    with pytest.raises(
        ValueError,
        match="do not map to approved products",
    ):
        import_local_snapshot(
            model_input_path=model_input_path,
            database_path=database_path,
            observation_date="2026-07-21",
            dry_run=True,
        )


def test_nonpositive_price_is_rejected(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    model_input_path = tmp_path / "model_input.csv"

    _seed_product(database_path)
    _write_model_input(
        model_input_path,
        price=0,
    )

    with pytest.raises(
        ValueError,
        match="missing or nonpositive prices",
    ):
        import_local_snapshot(
            model_input_path=model_input_path,
            database_path=database_path,
            observation_date="2026-07-21",
            dry_run=True,
        )


def test_import_creates_matching_source_run(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    source_path = tmp_path / "model_input.csv"

    _seed_product(database_path)
    _write_model_input(source_path)

    result = import_local_snapshot(
        model_input_path=source_path,
        database_path=database_path,
        observation_date="2026-07-21",
    )

    connection = sqlite3.connect(database_path)

    try:
        source_run = connection.execute(
            """
            SELECT
                source_run_id,
                source_name,
                status,
                records_processed
            FROM source_runs
            """
        ).fetchone()

        observation_runs = connection.execute(
            """
            SELECT DISTINCT source_run_id
            FROM price_observations
            """
        ).fetchall()
    finally:
        connection.close()

    assert result.inserted_rows == 1
    assert source_run == (
        "product_master_local_snapshot:2026-07-21",
        "product_master_local_snapshot",
        "SUCCESS",
        1,
    )
    assert observation_runs == [
        (
            "product_master_local_snapshot:"
            "2026-07-21",
        )
    ]


def test_source_run_upsert_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal2.sqlite"
    source_path = tmp_path / "model_input.csv"

    _seed_product(database_path)
    _write_model_input(source_path)

    for _ in range(2):
        import_local_snapshot(
            model_input_path=source_path,
            database_path=database_path,
            observation_date="2026-07-21",
        )

    connection = sqlite3.connect(database_path)

    try:
        source_run_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM source_runs
            """
        ).fetchone()[0]

        observation_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM price_observations
            """
        ).fetchone()[0]

        semantic_orphans = connection.execute(
            """
            SELECT COUNT(*)
            FROM price_observations p
            LEFT JOIN source_runs s
              ON s.source_run_id = p.source_run_id
            WHERE p.source_run_id IS NOT NULL
              AND s.source_run_id IS NULL
            """
        ).fetchone()[0]
    finally:
        connection.close()

    assert source_run_count == 1
    assert observation_count == 1
    assert semantic_orphans == 0
