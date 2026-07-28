from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "build_phase_8_2_1d_2_secret_lair_historical_performance.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "phase_8_2_1d_2_builder",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_snapshot_is_not_historical_return() -> None:
    module = load_module()
    result = module.historical_metrics(
        [
            {
                "date": module.date(2026, 7, 23),
                "value": 100.0,
                "sources": ["tcgcsv"],
                "raw_observations": 1,
            }
        ]
    )

    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["eligible"] == "NO"
    assert "total_return_pct" not in result
    assert "cagr_pct" not in result


def test_dated_history_calculates_total_return_and_cagr() -> None:
    module = load_module()
    result = module.historical_metrics(
        [
            {
                "date": module.date(2024, 1, 1),
                "value": 100.0,
                "sources": ["source-a"],
                "raw_observations": 1,
            },
            {
                "date": module.date(2025, 1, 1),
                "value": 121.0,
                "sources": ["source-a"],
                "raw_observations": 1,
            },
        ]
    )

    assert result["status"] == "HISTORICAL_PERFORMANCE_READY"
    assert result["eligible"] == "YES"
    assert abs(result["total_return_pct"] - 21.0) < 0.0001
    assert 20.8 < result["cagr_pct"] < 21.2


def test_short_span_remains_suppressed() -> None:
    module = load_module()
    result = module.historical_metrics(
        [
            {
                "date": module.date(2026, 7, 1),
                "value": 100.0,
                "sources": ["source-a"],
                "raw_observations": 1,
            },
            {
                "date": module.date(2026, 7, 15),
                "value": 110.0,
                "sources": ["source-a"],
                "raw_observations": 1,
            },
        ]
    )

    assert result["status"] == "INSUFFICIENT_SPAN"
    assert result["eligible"] == "NO"


def test_build_preserves_forecast_boundary(tmp_path: Path, monkeypatch) -> None:
    module = load_module()

    evaluation = tmp_path / "evaluation.csv"
    history = tmp_path / "history.csv"
    output = tmp_path / "output"
    universal = tmp_path / "universal"
    uip = tmp_path / "uip"

    monkeypatch.setattr(module, "UNIVERSAL_LATEST", universal)
    monkeypatch.setattr(module, "UIP_LATEST", uip)

    with evaluation.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "investment_product_id",
                "canonical_product_name",
            ],
        )
        writer.writeheader()
        for index in range(973):
            writer.writerow(
                {
                    "investment_product_id": f"SL-{index:04d}",
                    "canonical_product_name": f"Product {index}",
                }
            )

    with history.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "observation_date",
                "secret_lair_id",
                "source_name",
                "market_price",
                "low_price",
                "source_record_id",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "observation_date": "2026-07-23",
                "secret_lair_id": "SL-0000",
                "source_name": "tcgcsv",
                "market_price": "100",
                "low_price": "90",
                "source_record_id": "1",
            }
        )

    result = module.build(history, evaluation, output)
    rows = list(
        csv.DictReader(
            (
                output
                / "secret_lair_historical_performance.csv"
            ).open(encoding="utf-8")
        )
    )

    assert result["status"] == "CERTIFIED"
    assert len(rows) == 973
    assert all(row["forecast_eligible"] == "NO" for row in rows)
    assert all(
        row["recommendation_eligible"] == "NO"
        for row in rows
    )
    assert all(not row["one_year_base_usd"] for row in rows)
    assert rows[0]["historical_performance_status"] in {
        "INSUFFICIENT_HISTORY",
        "NO_HISTORY",
    }
