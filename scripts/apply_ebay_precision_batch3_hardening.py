from __future__ import annotations

from pathlib import Path

SOURCE = Path("terminal2/market_sources/ebay_precision.py")
TESTS = Path("tests/test_ebay_matching_precision.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Could not find expected source block: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    source = replace_once(
        source,
        '    " theme booster ",\n    " set booster ",\n)',
        '    " theme booster ",\n    " set booster ",\n    " play booster ",\n)',
        "play booster exclusion",
    )

    old_conflicts = '''def _has_conflicting_set_identity(
    product: base.CanonicalProduct,
    title_norm: str,
) -> bool:
    product_name = base._norm(product.canonical_product_name)

    if (
        " commander legends " in product_name
        and " battle for baldur s gate " not in product_name
        and " battle for baldur s gate " in title_norm
    ):
        return True

    if product_name.strip() == "dominaria booster box":
        return any(
            phrase in title_norm
            for phrase in (
                " dominaria remastered ",
                " dominaria united ",
            )
        )

    return False
'''

    new_conflicts = '''def _has_conflicting_set_identity(
    product: base.CanonicalProduct,
    title_norm: str,
) -> bool:
    product_name = base._norm(product.canonical_product_name)
    product_key = product_name.strip()

    conflict_phrases: dict[str, tuple[str, ...]] = {
        "commander legends collector booster display": (
            " battle for baldur s gate ",
        ),
        "dominaria booster box": (
            " dominaria remastered ",
            " dominaria united ",
        ),
        "innistrad booster box": (
            " innistrad remastered ",
            " innistrad midnight hunt ",
            " innistrad crimson vow ",
        ),
        "lorwyn booster box": (
            " lorwyn eclipsed ",
        ),
        "modern horizons booster box": (
            " modern horizons 2 ",
            " modern horizons 3 ",
        ),
    }

    return any(
        phrase in title_norm
        for phrase in conflict_phrases.get(product_key, ())
    )
'''

    source = replace_once(
        source,
        old_conflicts,
        new_conflicts,
        "generalized conflicting set identity",
    )

    SOURCE.write_text(source, encoding="utf-8")

    tests = TESTS.read_text(encoding="utf-8")
    marker = "\ndef test_precision_runner_uses_strict_matcher_without_recursion"
    additions = '''

def test_play_booster_box_is_rejected_for_historical_box():
    result = strict_match_listing(
        product("Lorwyn - Booster Box"),
        listing("MTG Lorwyn Eclipsed Play Booster Box Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_innistrad_remastered_is_rejected_for_original_innistrad():
    result = strict_match_listing(
        product("Innistrad - Booster Box"),
        listing("MTG Innistrad Remastered Collector Booster Box New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_midnight_hunt_is_rejected_for_original_innistrad():
    result = strict_match_listing(
        product("Innistrad - Booster Box"),
        listing("MTG Innistrad Midnight Hunt Collector Booster Box Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_lorwyn_eclipsed_is_rejected_for_original_lorwyn():
    result = strict_match_listing(
        product("Lorwyn - Booster Box"),
        listing("MTG Lorwyn Eclipsed Collector Booster Box Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_modern_horizons_three_is_rejected_for_original_modern_horizons():
    result = strict_match_listing(
        product("Modern Horizons - Booster Box"),
        listing("MTG Modern Horizons 3 Play Booster Box Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons
'''

    if "test_play_booster_box_is_rejected_for_historical_box" not in tests:
        if marker not in tests:
            raise RuntimeError("Could not find test insertion marker")
        tests = tests.replace(marker, additions + marker, 1)
        TESTS.write_text(tests, encoding="utf-8")

    print("Batch 3 eBay precision hardening applied.")
    print(f"Updated: {SOURCE}")
    print(f"Updated: {TESTS}")


if __name__ == "__main__":
    main()
