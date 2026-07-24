from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")
TEST_PATH = Path("tests/test_ebay_matching_precision.py")
AUDIT_PATH = Path("scripts/audit_ebay_matching_batch.py")

PAIR_LINES = (
    '        (" brain dead creatures ", " brain dead lands "),\n',
    '        (" heroic deeds ", " villainous plots "),\n',
    '        (" venom unleashed colors ", " venom unleashed inks "),\n',
)

SPECIAL_RULES = '''
    # Arcane and Arcane: Lands are separate sealed products.
    product_arcane_lands = " secret lair x arcane lands " in product_norm
    title_arcane_lands = " secret lair x arcane lands " in title_norm
    product_arcane_base = " secret lair x arcane " in product_norm and not product_arcane_lands
    title_arcane_base = " secret lair x arcane " in title_norm and not title_arcane_lands
    if (product_arcane_base and title_arcane_lands) or (product_arcane_lands and title_arcane_base):
        return True

    # Death Is in the Eyes of the Beholder I and II must agree explicitly.
    product_beholder = re.search(r" death is in the eyes of the beholder (i{1,2}) ", product_norm)
    title_beholder = re.search(r" death is in the eyes of the beholder (i{1,2}) ", title_norm)
    if product_beholder and title_beholder and product_beholder.group(1) != title_beholder.group(1):
        return True

    # Monty Python Holy Grail Vol. 1 and Vol. 2 must agree explicitly.
    product_monty_volume = re.search(r" holy grail vol (1|2) ", product_norm)
    title_monty_volume = re.search(r" holy grail vol (1|2) ", title_norm)
    if product_monty_volume and title_monty_volume and product_monty_volume.group(1) != title_monty_volume.group(1):
        return True

    # A Twisted Metal promo cannot map to the generic Secret Lair promo Sol Ring.
    product_twisted_metal = " twisted metal " in product_norm
    title_twisted_metal = " twisted metal " in title_norm
    product_promo_sol_ring = " promo " in product_norm and " sol ring " in product_norm
    title_promo_sol_ring = " promo " in title_norm and " sol ring " in title_norm
    if product_promo_sol_ring and title_promo_sol_ring and product_twisted_metal != title_twisted_metal:
        return True

    # Venom Unleashed Colors/Inks canonicals require the listing to identify the variant.
    if " venom unleashed " in product_norm:
        product_venom_colors = " venom unleashed colors " in product_norm
        product_venom_inks = " venom unleashed inks " in product_norm
        title_venom_colors = " venom unleashed colors " in title_norm
        title_venom_inks = " venom unleashed inks " in title_norm
        if (product_venom_colors or product_venom_inks) and not (title_venom_colors or title_venom_inks):
            return True
'''

TEST_BLOCK = '''


def test_secret_lair_brain_dead_creatures_lands_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Brain Dead: Creatures - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("MTG Secret Lair x Brain Dead: Lands Rainbow Foil Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_arcane_base_lands_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Arcane - Traditional Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair x Arcane: Lands Traditional Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_spiderman_heroic_villainous_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Marvel's Spider-Man: Heroic Deeds - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Spider-Man Villainous Plots Rainbow Foil Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_beholder_volume_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Dungeons & Dragons: Death is in the Eyes of the Beholder II - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Dungeons & Dragons Death is in the Eyes of the Beholder I Foil"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_monty_python_volume_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Monty Python: Monty Python and the Holy Grail: Vol. 1 - Traditional Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Monty Python and the Holy Grail Vol. 2 Foil Edition Box"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_venom_colors_inks_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Marvel's Spider-Man: Venom Unleashed (Colors) - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Spider-Man Venom Unleashed Inks Rainbow Foil Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_venom_generic_variant_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Marvel's Spider-Man: Venom Unleashed (Colors) - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Spider-Man Venom Unleashed Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_twisted_metal_sol_ring_does_not_match_generic_promo():
    result = strict_match_listing(
        product("Drop: Secret Lair Promo: Sol Ring - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("MTG Sol Ring Rainbow Foil Secret Lair Promo Twisted Metal Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
'''


def apply() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")

    pair_anchor = '        (" li l er walkers ", " li l est walkers "),\n'
    if pair_anchor not in precision:
        raise RuntimeError("Expected paired-identity anchor not found")
    for pair_line in PAIR_LINES:
        if pair_line not in precision:
            precision = precision.replace(pair_anchor, pair_anchor + pair_line, 1)

    special_anchor = '    product_second_helpings = " just add milk second helpings " in product_norm\n'
    if SPECIAL_RULES.strip() not in precision:
        if special_anchor not in precision:
            raise RuntimeError("Expected Secret Lair variant anchor not found")
        precision = precision.replace(special_anchor, SPECIAL_RULES + "\n" + special_anchor, 1)

    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    if "test_secret_lair_brain_dead_creatures_lands_collision_is_rejected" not in tests:
        tests = tests.rstrip() + TEST_BLOCK + "\n"
    TEST_PATH.write_text(tests, encoding="utf-8")

    audit = AUDIT_PATH.read_text(encoding="utf-8")
    old_norm = 'def norm(value: str | None) -> str:\n    return re.sub(r"\\s+", " ", (value or "").strip())\n'
    new_norm = '''def norm(value: str | None) -> str:\n    text = (value or "").translate(str.maketrans({"‑": "-", "–": "-", "—": "-", "−": "-"}))\n    return re.sub(r"\\s+", " ", text.strip())\n'''
    if old_norm in audit:
        audit = audit.replace(old_norm, new_norm, 1)
    elif new_norm not in audit:
        raise RuntimeError("Expected audit norm function not found")
    AUDIT_PATH.write_text(audit, encoding="utf-8")

    print("SECRET LAIR BATCH 0430 COLLISION HARDENING: APPLIED")
    print(f"Matcher: {PRECISION_PATH}")
    print(f"Tests: {TEST_PATH}")
    print(f"Audit: {AUDIT_PATH}")
    print("Rules: Arcane Lands, Brain Dead, Beholder I/II, Spider-Man, Venom, Monty Python, Twisted Metal Sol Ring")
    print("Audit: Unicode non-foil hyphens normalized")


if __name__ == "__main__":
    apply()
