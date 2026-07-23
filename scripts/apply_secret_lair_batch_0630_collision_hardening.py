from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")
TEST_PATH = Path("tests/test_ebay_matching_precision.py")

RULE_BLOCK = '''
    # Showcase: Kaldheim Part 1 and Part 2 must agree explicitly.
    if " showcase kaldheim " in product_norm:
        product_kaldheim_part = re.search(r" showcase kaldheim part (1|2) ", product_norm)
        title_kaldheim_part = re.search(r" showcase kaldheim part (1|2) ", title_norm)
        if (
            product_kaldheim_part
            and title_kaldheim_part
            and product_kaldheim_part.group(1) != title_kaldheim_part.group(1)
        ):
            return True

    # Showcase: March of the Machine Vol. 1/2/3 must agree explicitly.
    if " showcase march of the machine vol " in product_norm:
        product_mom_volume = re.search(
            r" showcase march of the machine vol (1|2|3) ",
            product_norm,
        )
        title_mom_volume = re.search(
            r" showcase march of the machine vol (1|2|3) ",
            title_norm,
        )
        if (
            product_mom_volume
            and title_mom_volume
            and product_mom_volume.group(1) != title_mom_volume.group(1)
        ):
            return True

    # Read The Fine Print has distinct Foil Etched and Traditional Foil products.
    if " showcase read the fine print " in product_norm:
        product_read_etched = (
            " foil etched " in product_norm
            or " etched foil " in product_norm
        )
        product_read_traditional = " traditional foil " in product_norm
        title_read_etched = (
            " foil etched " in title_norm
            or " etched foil " in title_norm
        )
        title_read_traditional = " traditional foil " in title_norm
        if (product_read_etched and title_read_traditional) or (
            product_read_traditional and title_read_etched
        ):
            return True
'''

TEST_BLOCK = '''


def test_secret_lair_kaldheim_part_one_rejects_part_two_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: Kaldheim - Part 1 - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Showcase Kaldheim Part 2 Foil New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_kaldheim_part_two_allows_part_two_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: Kaldheim - Part 2 - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Showcase Kaldheim Part 2 Foil New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state != "REJECTED"


def test_secret_lair_march_machine_volume_one_rejects_volume_two_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: March of the Machine Vol. 1 - Halo Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Showcase March of the Machine Vol. 2 Halo Foil Secret Lair Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_march_machine_volume_two_allows_volume_two_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: March of the Machine Vol. 2 - Halo Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Showcase March of the Machine Vol. 2 Halo Foil Secret Lair Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state != "REJECTED"


def test_secret_lair_read_fine_print_traditional_rejects_etched_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: Read The Fine Print - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Secret Lair Showcase Read The Fine Print Foil Etched Edition New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_read_fine_print_etched_allows_etched_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: Read The Fine Print - Foil Etched Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Secret Lair Showcase Read The Fine Print Foil Etched Edition New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state != "REJECTED"
'''


def apply() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")

    anchor = '    product_second_helpings = " just add milk second helpings " in product_norm\n'
    if RULE_BLOCK.strip() not in precision:
        if anchor not in precision:
            raise RuntimeError("Expected Secret Lair variant anchor not found")
        precision = precision.replace(anchor, RULE_BLOCK + "\n" + anchor, 1)

    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    if "test_secret_lair_kaldheim_part_one_rejects_part_two_listing" not in tests:
        tests = tests.rstrip() + TEST_BLOCK + "\n"
    TEST_PATH.write_text(tests, encoding="utf-8")

    print("SECRET LAIR BATCH 0630 COLLISION HARDENING: APPLIED")
    print(f"Matcher: {PRECISION_PATH}")
    print(f"Tests: {TEST_PATH}")
    print("Rules: Kaldheim Part 1/2, March of the Machine Vol. 1/2/3, Read The Fine Print finishes")


if __name__ == "__main__":
    apply()
