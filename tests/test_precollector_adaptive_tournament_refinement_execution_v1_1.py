from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_precollector_adaptive_tournament_refinement_execution_v1_1.py"


def test_repair_script_exists() -> None:
    assert SCRIPT.is_file()


def test_repair_binds_selected_model() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'row.get("selected_model")' in text
    assert '"round_one_selected_model_binding_verified": True' in text


def test_repair_preserves_long_horizon_insufficient_evidence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'LONG_HORIZON_MONTE_CARLO_REQUIRED=TRUE' in text
    assert '{"Y3", "Y5"}' in text


def test_repair_does_not_authorize_forecasts() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'FINAL_WINNER_CERTIFICATION_AUTHORIZED=FALSE' in text
    assert 'FORECAST_AUTHORIZED=FALSE' in text


def test_repair_reuses_certified_base_execution() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "run_precollector_adaptive_tournament_refinement_execution.py" in text
    assert "subprocess.run" in text
