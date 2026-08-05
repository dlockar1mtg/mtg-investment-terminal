from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_owner_review_contract_exists():
    assert (ROOT / "config/mtg/standards/precollector_forecast_control_point_owner_review_contract_v1.json").is_file()


def test_owner_review_script_exists():
    assert (ROOT / "scripts/review_precollector_forecast_control_point_validation.py").is_file()


def test_review_is_read_only_and_fail_closed():
    text = (ROOT / "scripts/review_precollector_forecast_control_point_validation.py").read_text(encoding="utf-8")
    assert "forecast_execution_authorized\": False" in text
    assert "ranking_execution_authorized\": False" in text
    assert "purchase_analysis_authorized\": False" in text


def test_exact_validation_hash_is_bound():
    text = (ROOT / "config/mtg/standards/precollector_forecast_control_point_owner_review_contract_v1.json").read_text(encoding="utf-8")
    assert "f286938d3996bd2b167af138d9150cdf6ee6f5f7537df91287138b63d6006958" in text


def test_review_requires_one_critical_blocker():
    text = (ROOT / "scripts/review_precollector_forecast_control_point_validation.py").read_text(encoding="utf-8")
    assert "EXPECTED_ONE_CRITICAL_BLOCKER" in text
