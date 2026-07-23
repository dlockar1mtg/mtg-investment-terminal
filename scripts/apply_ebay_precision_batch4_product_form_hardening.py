from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")
TEST_PATH = Path("tests/test_ebay_matching_precision.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find expected {label} block")
    return text.replace(old, new, 1)


def main() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")
    precision = replace_once(
        precision,
        '    " starter deck ",\n    " blaster box ",\n',
        '    " starter deck ",\n    " theme deck ",\n    " battle pack ",\n    " blaster box ",\n',
        "non-box product terms",
    )
    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    insertion = '''\n\ndef test_battle_pack_display_is_rejected():
    result = strict_match_listing(
        product("Return to Ravnica - Booster Box"),
        listing("MTG Return to Ravnica Battle Pack Display Box New"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_theme_deck_display_is_rejected():
    result = strict_match_listing(
        product("Scourge - Booster Box"),
        listing("MTG Scourge Theme Deck Display Box Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons
'''
    marker = "\ndef test_precision_runner_uses_strict_matcher_without_recursion"
    if insertion.strip() not in tests:
        if marker not in tests:
            raise RuntimeError("Could not find test insertion point")
        tests = tests.replace(marker, insertion + marker, 1)
    TEST_PATH.write_text(tests, encoding="utf-8")

    print("Batch 4 product-form hardening applied.")
    print(f"Updated: {PRECISION_PATH}")
    print(f"Updated: {TEST_PATH}")


if __name__ == "__main__":
    main()
