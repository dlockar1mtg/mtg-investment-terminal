from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_final_champion_challenge_architecture_contract_v1.json"
BUILDER = ROOT / "scripts/build_precollector_final_champion_challenge_architecture.py"


def test_contract_exists_and_is_parseable():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["contract_id"] == "precollector_final_champion_challenge_architecture_v1"


def test_round_two_package_binding_is_exact():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    package = data["required_round_two_package"]
    assert package["package_name"] == "MTG_PreCollector_Adaptive_Tournament_Refinement_Execution_v1_1.zip"
    assert package["sha256"] == "f67f2c1f0241f9450498b4cf9cd584852766738e7a5b134591c0365b4bb7fc29"


def test_short_and_long_horizon_routes_are_separate():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["short_horizons"] == ["D90", "D180", "D365"]
    assert data["long_horizons"] == ["Y3", "Y5"]


def test_monte_carlo_requirement_is_preserved():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    routing = data["long_horizon_routing"]
    assert routing["required_simulations_per_product_horizon"] == 10000
    assert routing["required_horizons_days"] == [1095, 1825]
    assert routing["direct_backtest_champion_authorized"] is False


def test_candidate_set_is_frozen():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    design = data["challenge_design"]
    assert design["candidate_set_frozen_before_challenge"] is True
    assert design["no_new_parameter_tuning"] is True
    assert design["no_new_feature_tuning"] is True


def test_required_stress_partitions_exist():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    partitions = set(data["challenge_design"]["stress_partitions"])
    assert partitions == {"OUTER_ALL", "LATEST_TIME_STRESS", "PRODUCT_CONCENTRATION_STRESS"}


def test_no_forced_winner():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["challenge_design"]["no_forced_winner"] is True
    assert "GOVERNED_NO_PRODUCTION_CHAMPION" in data["allowed_challenge_decisions"]


def test_downstream_authorities_remain_false():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for key in [
        "final_winner_certification_authorized",
        "forecast_generation_authorized",
        "ranking_execution_authorized",
        "purchase_analysis_authorized",
        "purchase_recommendation_authorized",
        "automatic_purchase_execution_authorized",
        "uip_delivery_authorized",
    ]:
        assert data[key] is False


def test_builder_does_not_reference_network_or_upstream_execution():
    text = BUILDER.read_text(encoding="utf-8")
    assert "requests." not in text
    assert "subprocess" not in text
    assert "urllib" not in text
    assert "perform_live_network_collection" not in text


def test_builder_preserves_fold_membership_and_defers_execution():
    text = BUILDER.read_text(encoding="utf-8")
    assert '"preserved_fold_membership_changed": False' in text
    assert '"final_challenge_execution_performed": False' in text


def test_architecture_outputs_are_governed():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    outputs = data["outputs"]
    assert len(outputs) == 8
    assert outputs["challenge_group_registry_csv"].endswith(".csv")
    assert outputs["summary_json"].endswith(".json")
