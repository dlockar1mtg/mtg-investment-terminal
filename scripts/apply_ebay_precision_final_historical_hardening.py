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
        '    " empty box ",\n    " box topper only ",\n',
        '    " empty box ",\n    " box only ",\n    " retail cardboard ",\n    " walmart display ",\n    " box topper only ",\n',
        "non-box product terms",
    )

    precision = replace_once(
        precision,
        '        "modern horizons booster box": (\n            " modern horizons 2 ",\n            " modern horizons 3 ",\n        ),\n',
        '        "modern horizons booster box": (\n            " modern horizons 2 ",\n            " modern horizons 3 ",\n        ),\n        "theros booster box": (\n            " theros beyond death ",\n        ),\n        "zendikar booster box": (\n            " zendikar rising ",\n        ),\n',
        "set conflict map",
    )

    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    insertion = '''\n\ndef test_theros_beyond_death_is_rejected_for_original_theros():\n    result = strict_match_listing(\n        product("Theros - Booster Box"),\n        listing("MTG Theros Beyond Death Collector Booster Box 12 Pack English New"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "conflicting_set_identity" in result.exclusion_reasons\n\n\ndef test_zendikar_rising_is_rejected_for_original_zendikar():\n    result = strict_match_listing(\n        product("Zendikar - Booster Box"),\n        listing("MTG Zendikar Rising Collector Booster Box English Factory Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "conflicting_set_identity" in result.exclusion_reasons\n\n\ndef test_retail_cardboard_display_is_rejected():\n    result = strict_match_listing(\n        product("Time Spiral - Booster Box"),\n        listing("Magic the Gathering Time Spiral Booster Retail Cardboard Walmart Display Box MTG"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "excluded_product_form" in result.exclusion_reasons\n\n\ndef test_box_only_listing_is_rejected():\n    result = strict_match_listing(\n        product("Unhinged - Booster Box"),\n        listing("Magic The Gathering MTG Unhinged Booster Box Box Only"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "excluded_product_form" in result.exclusion_reasons\n\n\ndef test_factory_sealed_unstable_unset_remains_accepted():\n    result = strict_match_listing(\n        product("Unstable - Booster Box"),\n        listing("MTG Unstable Booster Box Factory Sealed Unopened Magic The Gathering Un-Set"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "ACCEPTED"\n'''

    marker = "\ndef test_precision_runner_uses_strict_matcher_without_recursion"
    if insertion.strip() not in tests:
        if marker not in tests:
            raise RuntimeError("Could not find test insertion point")
        tests = tests.replace(marker, insertion + marker, 1)

    TEST_PATH.write_text(tests, encoding="utf-8")

    print("Final historical eBay precision hardening applied.")
    print(f"Updated: {PRECISION_PATH}")
    print(f"Updated: {TEST_PATH}")


if __name__ == "__main__":
    main()
