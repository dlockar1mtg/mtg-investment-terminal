from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHER = ROOT / "terminal2/market_sources/ebay_precision.py"
TESTS = ROOT / "tests/test_ebay_matching_precision.py"

HELPER = '''\n\ndef _secret_lair_foil_subtype(value_norm: str) -> str | None:\n    if " double rainbow foil " in value_norm:\n        return "double_rainbow"\n    if " rainbow foil " in value_norm:\n        return "rainbow"\n    if " traditional foil " in value_norm:\n        return "traditional"\n    return None\n'''

CONFLICT_INSERT = '''\n    product_foil_subtype = _secret_lair_foil_subtype(product_norm)\n    title_foil_subtype = _secret_lair_foil_subtype(title_norm)\n    if (\n        product_foil_subtype is not None\n        and title_foil_subtype is not None\n        and product_foil_subtype != title_foil_subtype\n    ):\n        return True\n'''

TEST_BLOCK = '''\n\ndef test_secret_lair_traditional_foil_rejects_explicit_rainbow_foil_listing():\n    result = strict_match_listing(\n        product(\n            "Drop: Aether Drifters - Traditional Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing(\n            "MTG Secret Lair Aether Drifters Rainbow Foil Sealed in Hand"\n        ),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_rainbow_foil_rejects_explicit_traditional_foil_listing():\n    result = strict_match_listing(\n        product(\n            "Drop: Arcade Racers - Rainbow Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing(\n            "MTG Secret Lair Arcade Racers Traditional Foil Edition Sealed"\n        ),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_traditional_foil_allows_generic_foil_listing():\n    result = strict_match_listing(\n        product(\n            "Drop: Absolute Annihilation - Traditional Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing(\n            "MTG Secret Lair Absolute Annihilation Foil Edition Sealed"\n        ),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "ACCEPTED"\n'''


def main() -> int:
    matcher = MATCHER.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")

    if "def _secret_lair_foil_subtype(" not in matcher:
        anchor = "\ndef _secret_lair_variant_conflict("
        if anchor not in matcher:
            raise SystemExit("Could not find Secret Lair variant-conflict helper.")
        matcher = matcher.replace(anchor, HELPER + anchor, 1)

    if "product_foil_subtype = _secret_lair_foil_subtype(product_norm)" not in matcher:
        anchor = '    product_nonfoil = " non foil " in product_norm\n'
        if anchor not in matcher:
            raise SystemExit("Could not find Secret Lair finish-conflict anchor.")
        matcher = matcher.replace(anchor, CONFLICT_INSERT + "\n" + anchor, 1)

    if "test_secret_lair_traditional_foil_rejects_explicit_rainbow_foil_listing" not in tests:
        tests = tests.rstrip() + TEST_BLOCK + "\n"

    MATCHER.write_text(matcher, encoding="utf-8")
    TESTS.write_text(tests, encoding="utf-8")

    print("SECRET LAIR FOIL SUBTYPE HARDENING: APPLIED")
    print(r"Matcher: terminal2\market_sources\ebay_precision.py")
    print(r"Tests: tests\test_ebay_matching_precision.py")
    print("Rule: explicit Traditional, Rainbow, and Double Rainbow conflicts reject")
    print("Generic Foil remains compatible when no subtype is stated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
