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

    helper_block = '''\n\nSECRET_LAIR_ZODIAC_SIGNS = (\n    "aquarius",\n    "aries",\n    "cancer",\n    "capricorn",\n    "gemini",\n    "leo",\n    "libra",\n    "pisces",\n    "sagittarius",\n    "scorpio",\n    "taurus",\n    "virgo",\n)\n\n\ndef _secret_lair_variant_conflict(\n    product: base.CanonicalProduct,\n    title_norm: str,\n) -> bool:\n    product_norm = base._norm(product.canonical_product_name)\n\n    product_nonfoil = " non foil " in product_norm\n    product_foil = (\n        " traditional foil " in product_norm\n        or (" foil " in product_norm and not product_nonfoil)\n    )\n    title_nonfoil = " non foil " in title_norm or " nonfoil " in title_norm\n    title_foil = (\n        " traditional foil " in title_norm\n        or (" foil " in title_norm and not title_nonfoil)\n    )\n    if product_nonfoil and title_foil:\n        return True\n    if product_foil and title_nonfoil:\n        return True\n\n    product_sign = next(\n        (sign for sign in SECRET_LAIR_ZODIAC_SIGNS if f" {sign} " in product_norm),\n        None,\n    )\n    if product_sign is not None:\n        listed_signs = {\n            sign\n            for sign in SECRET_LAIR_ZODIAC_SIGNS\n            if f" {sign} " in title_norm\n        }\n        if listed_signs and listed_signs != {product_sign}:\n            return True\n\n    if " book club bundle " in product_norm and " book club " not in title_norm:\n        return True\n\n    return False\n\n\ndef _secret_lair_strong_identity(\n    product: base.CanonicalProduct,\n    title_norm: str,\n) -> bool:\n    product_norm = base._norm(product.canonical_product_name)\n    if " secret lair " not in title_norm or " sealed " not in title_norm:\n        return False\n    if _token_coverage(product, title_norm) < 0.70:\n        return False\n\n    product_sign = next(\n        (sign for sign in SECRET_LAIR_ZODIAC_SIGNS if f" {sign} " in product_norm),\n        None,\n    )\n    if product_sign is not None and f" {product_sign} " not in title_norm:\n        return False\n\n    if " book club bundle " in product_norm and " book club " not in title_norm:\n        return False\n\n    product_nonfoil = " non foil " in product_norm\n    product_foil = (\n        " traditional foil " in product_norm\n        or (" foil " in product_norm and not product_nonfoil)\n    )\n    if product_nonfoil and not (\n        " non foil " in title_norm or " nonfoil " in title_norm\n    ):\n        return False\n    if product_foil and " foil " not in title_norm:\n        return False\n\n    return True\n'''

    precision = replace_once(
        precision,
        '\n\ndef strict_match_listing(\n',
        helper_block + '\n\ndef strict_match_listing(\n',
        "Secret Lair helper insertion point",
    )

    old_tail = '''        elif _is_ambiguous_display_case(title_norm):\n            reasons.append("ambiguous_display_case")\n            score = min(score, 0.75)\n            state = "REVIEW"\n\n    return replace(\n'''
    new_tail = '''        elif _is_ambiguous_display_case(title_norm):\n            reasons.append("ambiguous_display_case")\n            score = min(score, 0.75)\n            state = "REVIEW"\n\n    elif product.product_class == "SEALED_SECRET_LAIR":\n        if _secret_lair_variant_conflict(product, title_norm):\n            reasons.append("secret_lair_variant_conflict")\n            score = min(score, 0.49)\n            state = "REJECTED"\n        elif _secret_lair_strong_identity(product, title_norm) and not reasons:\n            score = max(score, 0.82)\n            state = "ACCEPTED"\n\n    return replace(\n'''
    precision = replace_once(
        precision,
        old_tail,
        new_tail,
        "strict matcher tail",
    )

    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    insertion = '''\n\ndef test_secret_lair_nonfoil_rejects_foil_variant():\n    result = strict_match_listing(\n        product(\n            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Non-Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Astrology Lands Aquarius Foil Edition Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_foil_rejects_nonfoil_variant():\n    result = strict_match_listing(\n        product(\n            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Astrology Lands Aquarius Non-Foil Edition Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_rejects_wrong_astrology_sign():\n    result = strict_match_listing(\n        product(\n            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Astrology Lands Pisces Foil Edition Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_book_club_requires_book_club_identity():\n    result = strict_match_listing(\n        product(\n            "Secret Lair Countdown Kit: An Encyclopedia of Magic Book Club Bundle",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Countdown Kit An Encyclopedia of Magic Factory Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "secret_lair_variant_conflict" in result.exclusion_reasons\n\n\ndef test_secret_lair_exact_astrology_variant_can_be_accepted():\n    result = strict_match_listing(\n        product(\n            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing("MTG Secret Lair Drop Astrology Lands Aquarius Traditional Foil Edition Sealed"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "ACCEPTED"\n'''

    marker = "\ndef test_precision_runner_uses_strict_matcher_without_recursion"
    if insertion.strip() not in tests:
        if marker not in tests:
            raise RuntimeError("Could not find test insertion point")
        tests = tests.replace(marker, insertion + marker, 1)

    TEST_PATH.write_text(tests, encoding="utf-8")

    print("Secret Lair Batch 1 identity hardening applied.")
    print(f"Updated: {PRECISION_PATH}")
    print(f"Updated: {TEST_PATH}")


if __name__ == "__main__":
    main()
