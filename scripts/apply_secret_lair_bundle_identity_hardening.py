from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHER = ROOT / "terminal2/market_sources/ebay_precision.py"
TESTS = ROOT / "tests/test_ebay_matching_precision.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not locate {label}")
    return text.replace(old, new, 1)


def main() -> None:
    matcher = MATCHER.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")

    old_conflict_tail = '''    if " book club bundle " in product_norm and " book club " not in title_norm:\n        return True\n\n    return False\n'''
    new_conflict_tail = '''    if " book club bundle " in product_norm and " book club " not in title_norm:\n        return True\n\n    product_is_bundle = " bundle " in product_norm\n    title_is_bundle = " bundle " in title_norm\n    if product_is_bundle and not title_is_bundle:\n        return True\n    if not product_is_bundle and title_is_bundle:\n        return True\n\n    return False\n'''
    matcher = replace_once(
        matcher,
        old_conflict_tail,
        new_conflict_tail,
        "Secret Lair conflict tail",
    )

    old_strong_tail = '''    if " book club bundle " in product_norm and " book club " not in title_norm:\n        return False\n\n    product_nonfoil = " non foil " in product_norm\n'''
    new_strong_tail = '''    if " book club bundle " in product_norm and " book club " not in title_norm:\n        return False\n\n    product_is_bundle = " bundle " in product_norm\n    title_is_bundle = " bundle " in title_norm\n    if product_is_bundle != title_is_bundle:\n        return False\n\n    product_nonfoil = " non foil " in product_norm\n'''
    matcher = replace_once(
        matcher,
        old_strong_tail,
        new_strong_tail,
        "Secret Lair strong identity tail",
    )

    insertion_point = '''def test_secret_lair_exact_astrology_variant_can_be_accepted():\n'''
    new_tests = '''def test_secret_lair_bundle_rejects_individual_drop_listing():\n    result = strict_match_listing(\n        product(\n            "Secret Lair Drop: Astrology Lands (Aries) Bundle - Non-Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Astrology Lands Aries Non-Foil Edition Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_individual_drop_rejects_bundle_listing():\n    result = strict_match_listing(\n        product(\n            "Secret Lair Drop: Astrology Lands (Aries) - Non-Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Astrology Lands Aries Non-Foil Bundle Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_exact_bundle_identity_can_be_accepted():\n    result = strict_match_listing(\n        product(\n            "Secret Lair Drop: Astrology Lands (Aries) Bundle - Non-Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Astrology Lands Aries Non-Foil Bundle Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "ACCEPTED"\n\n\n'''
    if "test_secret_lair_bundle_rejects_individual_drop_listing" not in tests:
        tests = replace_once(
            tests,
            insertion_point,
            new_tests + insertion_point,
            "Secret Lair exact variant test",
        )

    MATCHER.write_text(matcher, encoding="utf-8")
    TESTS.write_text(tests, encoding="utf-8")

    print("SECRET LAIR BUNDLE IDENTITY HARDENING: APPLIED")
    print(f"Matcher: {MATCHER.relative_to(ROOT)}")
    print(f"Tests: {TESTS.relative_to(ROOT)}")
    print("Rules: bundle requires bundle; individual drop rejects bundle")


if __name__ == "__main__":
    main()
