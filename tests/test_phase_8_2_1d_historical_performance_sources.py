from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "audit_phase_8_2_1d_historical_performance_sources.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "phase_8_2_1d_audit",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_semantic_field_separation() -> None:
    module = load_module()
    assert (
        module.field_class("realized_cagr_pct")
        == "HISTORICAL_PERFORMANCE"
    )
    assert (
        module.field_class("three_year_base_usd")
        == "FORWARD_FORECAST"
    )
    assert (
        module.field_class("observation_date")
        == "DATE_OR_PERIOD"
    )
    assert (
        module.field_class("current_market_value_usd")
        == "PRICE_OR_VALUE"
    )


def test_historical_terms_do_not_imply_forecast() -> None:
    module = load_module()
    assert (
        module.field_class("historical_annualized_return_pct")
        == "HISTORICAL_PERFORMANCE"
    )
    assert (
        module.field_class("five_year_projected_return_pct")
        == "FORWARD_FORECAST"
    )

def test_forward_qualifiers_override_generic_return_terms() -> None:
    module = load_module()

    assert (
        module.field_class("projected_return_pct")
        == "FORWARD_FORECAST"
    )
    assert (
        module.field_class("one_year_return_pct")
        == "FORWARD_FORECAST"
    )
    assert (
        module.field_class("three_year_projected_cagr_pct")
        == "FORWARD_FORECAST"
    )


def test_unqualified_realized_returns_remain_historical() -> None:
    module = load_module()

    assert (
        module.field_class("realized_return_pct")
        == "HISTORICAL_PERFORMANCE"
    )
    assert (
        module.field_class("historical_cagr_pct")
        == "HISTORICAL_PERFORMANCE"
    )
    assert (
        module.field_class("annualized_return_pct")
        == "HISTORICAL_PERFORMANCE"
    )


def test_read_text_is_memory_bounded(tmp_path: Path) -> None:
    module = load_module()

    source = tmp_path / "large.txt"
    source.write_text(
        "A" * 10_000,
        encoding="utf-8",
    )

    sampled = module.read_text(
        source,
        max_bytes=128,
    )

    assert len(sampled.encode("utf-8")) <= 128


def test_read_csv_respects_sample_limit(tmp_path: Path) -> None:
    module = load_module()

    source = tmp_path / "sample.csv"
    source.write_text(
        "product_id,value\n"
        + "\n".join(
            f"P-{index},{index}"
            for index in range(20)
        )
        + "\n",
        encoding="utf-8",
    )

    rows = module.read_csv(
        source,
        max_rows=5,
    )

    assert len(rows) == 5
    assert rows[0]["product_id"] == "P-0"
    assert rows[-1]["product_id"] == "P-4"
