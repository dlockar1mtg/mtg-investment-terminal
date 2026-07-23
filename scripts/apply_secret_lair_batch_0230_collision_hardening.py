from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")
TEST_PATH = Path("tests/test_ebay_matching_precision.py")

PAIR_INSERTS = (
    '        (" just add milk ", " just add milk second helpings "),\n',
    '        (" li l er walkers ", " li l est walkers "),\n',
)

PIXEL_RULE = '''\n    if " pixelsnowlands jpg " in product_norm:\n        product_pixel_subtype = _secret_lair_foil_subtype(product_norm)\n        title_pixel_subtype = _secret_lair_foil_subtype(title_norm)\n        title_has_generic_foil = " foil " in title_norm\n        if (\n            product_pixel_subtype in {"traditional", "etched"}\n            and title_has_generic_foil\n            and title_pixel_subtype is None\n        ):\n            return True\n'''

TEST_BLOCK = """


def test_secret_lair_just_add_milk_second_helpings_collision_is_rejected():
    result = strict_match_listing(
        product(
            "Drop: Just Add Milk - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Just Add Milk Second Helpings Non Foil Secret Lair New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_liler_lilest_walkers_collision_is_rejected():
    result = strict_match_listing(
        product(
            "Drop: Li'l'er Walkers - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Drop Li'l'est Walkers Non Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_pixelsnowlands_generic_foil_rejects_etched_canonical():
    result = strict_match_listing(
        product(
            "Drop: PixelSnowLands.jpg - Foil Etched Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair PixelSnowLands.jpg Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_pixelsnowlands_generic_foil_rejects_traditional_canonical():
    result = strict_match_listing(
        product(
            "Drop: PixelSnowLands.jpg - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair PixelSnowLands.jpg Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons
"""


def apply() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")

    tuple_anchor = '        (" kevin eastman colors ", " kevin eastman inks "),\n'
    if tuple_anchor not in precision:
        raise RuntimeError("Expected identity-pair anchor not found")

    for pair_line in PAIR_INSERTS:
        if pair_line not in precision:
            precision = precision.replace(tuple_anchor, tuple_anchor + pair_line, 1)

    pixel_anchor = "    product_foil_subtype = _secret_lair_foil_subtype(product_norm)\n"
    if PIXEL_RULE.strip() not in precision:
        if pixel_anchor not in precision:
            raise RuntimeError("Expected foil-subtype anchor not found")
        precision = precision.replace(pixel_anchor, PIXEL_RULE + "\n" + pixel_anchor, 1)

    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    if "test_secret_lair_just_add_milk_second_helpings_collision_is_rejected" not in tests:
        tests = tests.rstrip() + TEST_BLOCK + "\n"
    TEST_PATH.write_text(tests, encoding="utf-8")

    print("SECRET LAIR BATCH 0230 COLLISION HARDENING: APPLIED")
    print(f"Matcher: {PRECISION_PATH}")
    print(f"Tests: {TEST_PATH}")
    print("Rules: Just Add Milk/Second Helpings, Li'l'er/Li'l'est, PixelSnowLands generic foil ambiguity")


if __name__ == "__main__":
    apply()
