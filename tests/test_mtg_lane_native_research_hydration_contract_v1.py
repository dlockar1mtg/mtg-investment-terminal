import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "mtg_lane_native_research_hydration_contract_v1.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_hydration_contract_common_authority() -> None:
    doc = load()

    assert (
        doc["status"]
        == "AUTHORIZED_FOR_BOUNDED_UIP_HYDRATION_IMPLEMENTATION"
    )

    assert doc["common_interface"]["field_count"] == 23
    assert doc["common_interface"]["remains_frozen"] is True
    assert doc["common_interface"]["replaced_by_sidecars"] is False

    auth = doc["uip_authorization"]

    assert auth["may_load_product_research"] is True
    assert auth["may_load_horizon_research"] is True
    assert auth["may_attach_research_to_native_detail"] is True

    assert auth["may_modify_native_rank"] is False
    assert auth["may_modify_native_purchase_status"] is False
    assert auth["may_recalculate_forecast"] is False
    assert auth["may_recalculate_risk"] is False


def test_hydration_contract_collector_population() -> None:
    doc = load()

    product = doc["collector"]["product_dataset"]
    horizon = doc["collector"]["horizon_dataset"]

    assert product["row_count"] == 50
    assert product["analytical_core_count"] == 49
    assert product["current_price_only_count"] == 1

    assert (
        product["current_price_only_asset"]
        == "MTG-CANON-TCGPLAYER-515906"
    )

    assert horizon["row_count"] == 294
    assert horizon["product_count"] == 49

    assert horizon["horizons_days"] == [
        90,
        180,
        365,
        730,
        1095,
        1825,
    ]

    product_path = ROOT / product["path"]
    horizon_path = ROOT / horizon["path"]

    assert sha256(product_path) == product["sha256"]
    assert sha256(horizon_path) == horizon["sha256"]


def test_hydration_contract_precollector_population() -> None:
    doc = load()

    product = doc["pre_collector"]["product_dataset"]
    scenario = doc["pre_collector"]["scenario_dataset"]

    assert product["row_count"] == 131
    assert product["ranked_forecastable_count"] == 95
    assert product["not_ranked_count"] == 36

    assert scenario["row_count"] == 190
    assert scenario["product_count"] == 95
    assert scenario["horizons_years"] == [3, 5]

    product_path = ROOT / product["path"]
    scenario_path = ROOT / scenario["path"]

    assert sha256(product_path) == product["sha256"]
    assert sha256(scenario_path) == scenario["sha256"]


def test_hydration_contract_governance_boundaries() -> None:
    doc = load()

    required = set(doc["required_uip_behavior"])

    assert "HYDRATION_IS_PRESENTATION_ONLY" in required

    assert (
        "COMMON_23_FIELD_NATIVE_AUTHORITY_REMAINS_AUTHORITATIVE"
        in required
    )

    assert (
        "SIDECARS_SUPPLEMENT_BUT_DO_NOT_OVERRIDE_NATIVE_AUTHORITY"
        in required
    )

    assert (
        "MISSING_VALUES_MUST_NOT_CREATE_FAKE_CHART_POINTS"
        in required
    )

    forbidden = set(doc["forbidden"])

    assert "NO_MODEL_EXECUTION" in forbidden
    assert "NO_FORECAST_RECALCULATION" in forbidden
    assert "NO_RISK_RECALCULATION" in forbidden
    assert "NO_CRYPTO_BEAR_BASE_BULL_MAPPING" in forbidden
    assert "NO_CROSS_LANE_RANK" in forbidden
    assert "NO_CROSS_LANE_SCORE" in forbidden
    assert "NO_AUTOMATIC_PURCHASE_EXECUTION" in forbidden