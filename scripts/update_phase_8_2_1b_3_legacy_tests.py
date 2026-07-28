from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COLLECTOR_TEST = (
    ROOT
    / "tests"
    / "test_collector_booster_box_full_evaluation.py"
)

UNIFIED_TEST = (
    ROOT
    / "tests"
    / "test_unified_mtg_intelligence.py"
)


def replace_once(
    path: Path,
    old: str,
    new: str,
    label: str,
) -> None:
    text = path.read_text(
        encoding="utf-8-sig",
    )

    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one occurrence, "
            f"found {count}"
        )

    path.write_text(
        text.replace(old, new, 1),
        encoding="utf-8",
    )


replace_once(
    COLLECTOR_TEST,
    '    assert manifest["numeric_forecast_products"] == 47\n',
    (
        '    assert manifest["native_range_products"] == 48\n'
        '    assert manifest["observed_value_only_products"] == 0\n'
        '    assert manifest["suppressed_products"] == 1\n'
        '    assert manifest["certified_horizon_products"] == 0\n'
        '    assert manifest["recommendation_eligible_products"] == 0\n'
    ),
    "collector manifest assertions",
)

replace_once(
    UNIFIED_TEST,
    (
        '    assert '
        'manifest["numeric_forecast_counts"]'
        '["COLLECTOR_BOOSTER_BOX"] == 47\n'
    ),
    (
        '    assert '
        'manifest["numeric_forecast_counts"]'
        '["COLLECTOR_BOOSTER_BOX"] == 48\n'
    ),
    "unified collector native-range count",
)

print("=" * 78)
print("PHASE 8.2.1B.3 — LEGACY TEST CONTRACT UPDATE")
print("=" * 78)
print("PASS | collector manifest test now validates native ranges")
print("PASS | horizon forecast count expected to remain zero")
print("PASS | collector recommendation eligibility expected to remain zero")
print("PASS | unified collector native-range count updated to 48")
print("PHASE 8.2.1B.3 TEST UPDATE: PASS")
