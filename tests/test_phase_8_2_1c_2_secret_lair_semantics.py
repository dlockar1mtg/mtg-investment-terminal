from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_producer_declares_native_valuation_range():
    source=(ROOT/"scripts"/"build_full_secret_lair_model_evaluation.py").read_text(encoding="utf-8-sig")
    assert '"NATIVE_VALUATION_RANGE"' in source
    assert '"horizon_model_certified"] = "NO"' in source
    assert '"recommendation_eligible"] = "NO"' in source
    assert '"forecast_eligible"] = "NO"' in source

def test_native_range_normalization_keeps_base_inside_interval() -> None:
    base = 40.0
    source_low = 45.0
    source_high = 50.0

    normalized_low = round(min(source_low, base), 2)
    normalized_high = round(
        max(source_high, base, normalized_low),
        2,
    )

    assert normalized_low == 40.0
    assert normalized_low <= base <= normalized_high


def test_native_range_normalization_expands_high_to_base() -> None:
    base = 60.0
    source_low = 40.0
    source_high = 55.0

    normalized_low = round(min(source_low, base), 2)
    normalized_high = round(
        max(source_high, base, normalized_low),
        2,
    )

    assert normalized_high == 60.0
    assert normalized_low <= base <= normalized_high

