from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_unified_mtg_intelligence.py"
SPEC = importlib.util.spec_from_file_location("build_unified_mtg_intelligence", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_certifies_complete_universe() -> None:
    rows, diagnostics, manifest = MODULE.build()

    assert manifest["status"] == "CERTIFIED"
    assert len(rows) == 1141
    assert diagnostics == []
    assert manifest["lane_counts"] == {
        "COLLECTOR_BOOSTER_BOX": 49,
        "PRE_COLLECTOR_BOOSTER_BOX": 119,
        "SECRET_LAIR": 973,
    }


def test_universal_identity_and_privacy_contract() -> None:
    rows, _, _ = MODULE.build()

    ids = [row["universal_mtg_product_id"] for row in rows]
    assert len(ids) == len(set(ids)) == 1141
    assert all(row["currency"] == "USD" for row in rows)
    assert all(row["forecast_eligible"] in {"YES", "NO"} for row in rows)
    assert all(row["recommendation_eligible"] in {"YES", "NO"} for row in rows)

    prohibited = {
        "quantity",
        "acquisition_date",
        "total_cost_basis_usd",
        "notes",
    }
    assert all(prohibited.isdisjoint(row) for row in rows)


def test_certified_lane_forecast_and_recommendation_counts() -> None:
    _, _, manifest = MODULE.build()

    assert manifest["numeric_forecast_counts"]["SECRET_LAIR"] == 973
    assert manifest["numeric_forecast_counts"]["COLLECTOR_BOOSTER_BOX"] == 47
    assert manifest["numeric_forecast_counts"]["PRE_COLLECTOR_BOOSTER_BOX"] == 83
    assert manifest["recommendation_eligible_counts"]["COLLECTOR_BOOSTER_BOX"] == 36
    assert manifest["recommendation_eligible_counts"]["PRE_COLLECTOR_BOOSTER_BOX"] == 65


def test_lane_native_forecast_shapes_are_preserved() -> None:
    rows, _, _ = MODULE.build()

    secret = next(row for row in rows if row["lane"] == "SECRET_LAIR")
    collector = next(row for row in rows if row["lane"] == "COLLECTOR_BOOSTER_BOX")
    pre_collector = next(row for row in rows if row["lane"] == "PRE_COLLECTOR_BOOSTER_BOX")

    assert secret["native_forecast_base_usd"]
    assert not secret["one_year_base_usd"]

    assert collector["one_year_base_usd"] or collector["forecast_eligible"] == "NO"
    assert pre_collector["one_year_base_usd"] or pre_collector["forecast_eligible"] == "NO"
