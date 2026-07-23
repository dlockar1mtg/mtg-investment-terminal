from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")
TEST_PATH = Path("tests/test_ebay_matching_precision.py")

RULE = '''\n    if " death is in the eyes of the beholder " in product_norm:\n        product_is_one = (\n            " beholder i " in product_norm\n            or " beholder 1 " in product_norm\n        )\n        product_is_two = (\n            " beholder ii " in product_norm\n            or " beholder 2 " in product_norm\n        )\n        title_is_one = (\n            " beholder i " in title_norm\n            or " beholder 1 " in title_norm\n        )\n        title_is_two = (\n            " beholder ii " in title_norm\n            or " beholder 2 " in title_norm\n        )\n        if (product_is_one and title_is_two) or (product_is_two and title_is_one):\n            return True\n'''

TESTS = '''\n\n\ndef test_secret_lair_beholder_roman_two_rejects_numeric_one_listing():\n    result = strict_match_listing(\n        product(\n            "Drop: Secret Lair x Dungeons & Dragons: Death is in the Eyes of the Beholder II - Rainbow Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("FOIL Secret Lair x Dungeons & Dragons Death Is in the Eyes of the Beholder 1"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_beholder_roman_one_allows_numeric_one_listing():\n    result = strict_match_listing(\n        product(\n            "Drop: Secret Lair x Dungeons & Dragons: Death is in the Eyes of the Beholder I - Rainbow Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("FOIL Secret Lair x Dungeons & Dragons Death Is in the Eyes of the Beholder 1"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state != "REJECTED"\n'''


def apply() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")
    anchor = "    product_foil_subtype = _secret_lair_foil_subtype(product_norm)\n"
    if RULE.strip() not in precision:
        if anchor not in precision:
            raise RuntimeError("Expected matcher anchor not found")
        precision = precision.replace(anchor, RULE + "\n" + anchor, 1)
        PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    if "test_secret_lair_beholder_roman_two_rejects_numeric_one_listing" not in tests:
        tests = tests.rstrip() + TESTS + "\n"
        TEST_PATH.write_text(tests, encoding="utf-8")

    print("BEHOLDER NUMERIC VOLUME COLLISION REPAIR: APPLIED")
    print(f"Matcher: {PRECISION_PATH}")
    print(f"Tests: {TEST_PATH}")
    print("Rule: Beholder I/II now recognizes numeric 1/2 listing variants")


if __name__ == "__main__":
    apply()
