from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_final_champion_challenge_execution_contract_v1.json"
SCRIPT = ROOT / "scripts/run_precollector_final_champion_challenge_execution.py"


def contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_exists():
    assert CONTRACT.is_file()


def test_script_exists():
    assert SCRIPT.is_file()


def test_architecture_binding_is_exact():
    value = contract()["required_architecture_package"]
    assert value["package_name"] == "MTG_PreCollector_Final_Champion_Challenge_Architecture_v1.zip"
    assert value["sha256"] == "d4c23481c8010123fe3a24cb3abc32d2d8e8123398013594f3ddcc2876f2ba8f"


def test_round_two_binding_is_exact():
    value = contract()["required_round_two_package"]
    assert value["package_name"] == "MTG_PreCollector_Adaptive_Tournament_Refinement_Execution_v1_1.zip"
    assert value["sha256"] == "f67f2c1f0241f9450498b4cf9cd584852766738e7a5b134591c0365b4bb7fc29"


def test_expected_counts_are_governed():
    expected = contract()["expected_counts"]
    assert expected == {
        "short_horizon_challenge_groups": 9,
        "long_horizon_monte_carlo_routes": 6,
        "frozen_candidate_rows": 30,
        "stress_partition_rows": 27,
        "preserved_fold_rows": 1992,
    }


def test_three_stress_partitions_are_required():
    source = SCRIPT.read_text(encoding="utf-8")
    for name in ("OUTER_ALL", "LATEST_TIME_STRESS", "PRODUCT_CONCENTRATION_STRESS"):
        assert name in source


def test_candidate_set_remains_frozen():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"candidate_set_frozen": True' in source
    assert '"new_tuning_performed": False' in source


def test_long_horizon_monte_carlo_is_preserved():
    value = contract()["long_horizon_routing"]
    assert value["required_next_process"] == "PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE"
    assert value["required_simulations_per_product_horizon"] == 10000
    assert value["direct_backtest_champion_authorized"] is False


def test_final_authorities_remain_false():
    value = contract()
    for key in (
        "final_winner_certification_authorized",
        "forecast_generation_authorized",
        "ranking_execution_authorized",
        "purchase_analysis_authorized",
        "purchase_recommendation_authorized",
        "automatic_purchase_execution_authorized",
        "uip_delivery_authorized",
    ):
        assert value[key] is False


def test_no_forbidden_rebuild_or_network_logic():
    source = SCRIPT.read_text(encoding="utf-8").lower()
    assert "requests.get" not in source
    assert "subprocess" not in source


def test_next_stage_is_winner_and_uncertainty_certification():
    assert contract()["next_stage_if_certified"] == "PRECOLLECTOR_WINNER_AND_UNCERTAINTY_CERTIFICATION"
