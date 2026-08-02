from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_round3_final_champion_challenge_contract_v1.json"
SCRIPT = ROOT / "scripts/run_collector_v1_round3_final_champion_challenge.py"


def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_and_script_exist() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()


def test_round3_candidate_set_is_frozen() -> None:
    data = contract()
    assert data["governance"]["candidate_set_frozen_before_round3"] is True
    assert data["governance"]["no_new_feature_tuning"] is True


def test_round3_is_independent_by_horizon_and_route() -> None:
    data = contract()
    assert data["governance"]["independent_per_horizon"] is True
    assert data["governance"]["independent_per_route"] is True


def test_benchmark_and_stress_challenges_are_required() -> None:
    data = contract()
    governance = data["governance"]
    assert governance["benchmark_challenge_required"] is True
    assert governance["product_concentration_challenge_required"] is True
    assert governance["latest_time_stress_required"] is True
    assert set(data["challenge_partitions"]) == {
        "OUTER_ALL",
        "LATEST_TIME_STRESS",
        "PRODUCT_CONCENTRATION_STRESS",
    }


def test_current_only_features_remain_prohibited() -> None:
    data = contract()
    assert data["governance"]["current_only_features_prohibited"] is True
    script = SCRIPT.read_text(encoding="utf-8")
    assert '"current_only_features_used": False' in script


def test_purchase_authority_remains_closed() -> None:
    data = contract()
    assert data["governance"]["purchase_recommendations_authorized"] is False


def test_all_final_decisions_are_explicit() -> None:
    data = contract()
    assert set(data["allowed_final_decisions"]) == {
        "PROMOTE_ROUND2_CHAMPION",
        "PROMOTE_ROUND1_CHAMPION",
        "RETAIN_NAIVE_BASELINE",
        "GOVERNED_NO_PRODUCTION_CHAMPION",
    }


def test_required_group_counts_are_preserved() -> None:
    data = contract()
    assert data["required_group_decisions"] == 8
    assert data["preserved_governed_no_winner_groups"] == 10


def test_production_is_only_for_certified_champions() -> None:
    data = contract()
    assert data["governance"]["production_forecasting_authorized_only_for_certified_champions"] is True


def test_script_writes_required_outputs() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for name in (
        "collector_round3_challenge_evidence.csv",
        "collector_round3_final_champions.csv",
        "collector_round3_preserved_no_winner_groups.csv",
        "collector_round3_final_champion_challenge_summary.json",
    ):
        assert name in script
