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
        'def _is_mixed_product_listing(\n    product: base.CanonicalProduct,\n    title_norm: str,\n    raw_title: str,\n) -> bool:\n    raw_lower = raw_title.lower()\n    if "+" not in raw_title and " plus " not in raw_lower:\n        return False\n',
        'def _is_mixed_product_listing(\n    product: base.CanonicalProduct,\n    title_norm: str,\n    raw_title: str,\n) -> bool:\n    raw_lower = raw_title.lower()\n    has_connector = (\n        "+" in raw_title\n        or " plus " in raw_lower\n        or " & " in raw_title\n        or " and " in raw_lower\n    )\n    if not has_connector:\n        return False\n\n    if re.search(r"\\bbooster\\s+boxes?\\b.*\\bbooster\\s+boxes?\\b", title_norm):\n        return True\n',
        "mixed-product detector",
    )

    precision = replace_once(
        precision,
        'def _is_ambiguous_display_case(title_norm: str) -> bool:\n',
        'def _has_non_english_marker(title_norm: str, raw_title: str) -> bool:\n    raw_upper = raw_title.upper()\n    shorthand_markers = ("*JP*", "[JP]", "(JP)", " JP ", " JPN ")\n    if any(marker in raw_upper for marker in shorthand_markers):\n        return True\n    return any(\n        phrase in title_norm\n        for phrase in (\n            " japanese ",\n            " german ",\n            " french ",\n            " italian ",\n            " spanish ",\n            " portuguese ",\n            " korean ",\n            " chinese ",\n            " russian ",\n        )\n    )\n\n\ndef _is_ambiguous_display_case(title_norm: str) -> bool:\n',
        "language marker insertion point",
    )

    precision = replace_once(
        precision,
        '        if _is_mixed_product_listing(product, title_norm, result.title):\n            reasons.append("mixed_product_listing")\n',
        '        if _is_mixed_product_listing(product, title_norm, result.title):\n            reasons.append("mixed_product_listing")\n        if _has_non_english_marker(title_norm, result.title):\n            reasons.append("non_english")\n',
        "reason application",
    )

    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    insertion = '''\n\ndef test_ampersand_two_product_listing_is_rejected():\n    result = strict_match_listing(\n        product("Journey Into Nyx - Booster Box"),\n        listing("Magic the Gathering Journey into Nyx & Origins Booster Boxes JP NEW SEALED"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "mixed_product_listing" in result.exclusion_reasons\n\n\ndef test_jp_language_marker_is_rejected():\n    result = strict_match_listing(\n        product("Journey Into Nyx - Booster Box"),\n        listing("Magic the Gathering Journey into Nyx Booster Box *JP* NEW SEALED"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "non_english" in result.exclusion_reasons\n'''

    marker = "\ndef test_precision_runner_uses_strict_matcher_without_recursion"
    if insertion.strip() not in tests:
        if marker not in tests:
            raise RuntimeError("Could not find test insertion point")
        tests = tests.replace(marker, insertion + marker, 1)

    TEST_PATH.write_text(tests, encoding="utf-8")

    print("Batch 3 language and multi-product hardening applied.")
    print(f"Updated: {PRECISION_PATH}")
    print(f"Updated: {TEST_PATH}")


if __name__ == "__main__":
    main()
