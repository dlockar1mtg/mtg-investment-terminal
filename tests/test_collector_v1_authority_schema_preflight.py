from __future__ import annotations

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/inspect_collector_v1_authority_schemas.py"


def test_schema_preflight_exists_and_compiles() -> None:
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_schema_preflight_is_read_only_for_model_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "unlink(" not in text
    assert "np.random" not in text
    assert "collector_lorwyn_standalone_probabilistic_forecasts.csv" not in text
    assert "collector_final_integrated_49_product_forecasts.csv" not in text
    assert "No model execution, output invalidation, calibration, ranking, or purchasing occurred." in text


def test_schema_preflight_reports_dataset_specific_identity_modes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "CANONICAL_ID_PLUS_NAME",
        "CANONICAL_ID_ONLY",
        "TCGPLAYER_ID_PLUS_NAME",
        "TCGPLAYER_ID_ONLY",
        "NO_RECOGNIZED_IDENTITY_FIELDS",
        "collector_authority_schema_preflight.json",
    ]:
        assert token in text
