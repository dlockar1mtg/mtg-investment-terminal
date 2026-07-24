from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")
TEST_PATH = Path("tests/test_ebay_matching_precision.py")
AUDIT_PATH = Path("scripts/audit_ebay_matching_batch.py")

PAIR_RULE = '''\n\ndef _secret_lair_explicit_identity_conflict(product_norm: str, title_norm: str) -> bool:\n    paired_identities = (\n        (" cats are better than dogs ", " dogs are better than cats "),\n        (" allied talismans ", " enemy talismans "),\n        (" extra life 2020 ", " extra life 2022 "),\n        (" kevin eastman colors ", " kevin eastman inks "),\n    )\n    for left, right in paired_identities:\n        if left in product_norm and right in title_norm:\n            return True\n        if right in product_norm and left in title_norm:\n            return True\n    return False\n'''

PRECISION_INSERT = '''\n    if _secret_lair_explicit_identity_conflict(product_norm, title_norm):\n        return True\n'''

TESTS = r'''\n\ndef test_secret_lair_cats_dogs_title_collision_is_rejected():\n    result = strict_match_listing(\n        product(\n            "Drop: Cats Are Better Than Dogs - Non-Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Dogs Are Better Than Cats Non-Foil Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_allied_enemy_talisman_collision_is_rejected():\n    result = strict_match_listing(\n        product(\n            "Drop: Dan Frazier Is Back Again: The Enemy Talismans - Foil Etched Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("Secret Lair Dan Frazier Allied Talismans Foil Etched Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_extra_life_year_collision_is_rejected():\n    result = strict_match_listing(\n        product(\n            "Drop: Extra Life 2022 - Traditional Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Extra Life 2020 Traditional Foil Edition Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_kevin_eastman_colors_inks_collision_is_rejected():\n    result = strict_match_listing(\n        product(\n            "Drop: Featuring: Kevin Eastman (Colors) - Traditional Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("Secret Lair Featuring Kevin Eastman Inks Traditional Foil Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n'''


def apply() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")
    if "def _secret_lair_explicit_identity_conflict" not in precision:
        anchor = "def _secret_lair_variant_conflict("
        precision = precision.replace(anchor, PAIR_RULE + "\n\n" + anchor, 1)
    if "_secret_lair_explicit_identity_conflict(product_norm, title_norm)" not in precision:
        anchor = "    product_norm = base._norm(product.canonical_product_name)\n"
        precision = precision.replace(anchor, anchor + PRECISION_INSERT, 1)
    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    if "test_secret_lair_cats_dogs_title_collision_is_rejected" not in tests:
        tests = tests.rstrip() + TESTS + "\n"
    TEST_PATH.write_text(tests, encoding="utf-8")

    audit = AUDIT_PATH.read_text(encoding="utf-8")
    audit = audit.replace('"opened"', 'r"\\bopened\\b"')
    audit = audit.replace("'opened'", "r'\\bopened\\b'")
    AUDIT_PATH.write_text(audit, encoding="utf-8")

    print("SECRET LAIR IDENTITY COLLISION HARDENING: APPLIED")
    print(f"Matcher: {PRECISION_PATH}")
    print(f"Tests: {TEST_PATH}")
    print(f"Audit: {AUDIT_PATH}")
    print("Rules: cats/dogs, allied/enemy, Extra Life year, Eastman colors/inks")
    print("Audit fix: unopened no longer matches opened")


if __name__ == "__main__":
    apply()
