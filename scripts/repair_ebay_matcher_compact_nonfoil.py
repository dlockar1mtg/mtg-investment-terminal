from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRECISION = ROOT / "terminal2/market_sources/ebay_precision.py"
TESTS = ROOT / "tests/test_ebay_matching_precision.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Expected {label} anchor not found")
    return text.replace(old, new, 1)


def apply_precision() -> None:
    text = PRECISION.read_text(encoding="utf-8")

    old_variant = '''    product_nonfoil = " non foil " in product_norm
    product_foil = (
        " traditional foil " in product_norm
        or (" foil " in product_norm and not product_nonfoil)
    )
    title_nonfoil = " non foil " in title_norm or " nonfoil " in title_norm
'''
    new_variant = '''    product_nonfoil = " non foil " in product_norm or " nonfoil " in product_norm
    product_foil = (
        " traditional foil " in product_norm
        or (" foil " in product_norm and not product_nonfoil)
    )
    title_nonfoil = " non foil " in title_norm or " nonfoil " in title_norm
'''
    text = replace_once(text, old_variant, new_variant, "variant compact nonfoil")

    old_strong = '''    product_nonfoil = " non foil " in product_norm
    product_foil = (
        " traditional foil " in product_norm
        or (" foil " in product_norm and not product_nonfoil)
    )
'''
    new_strong = '''    product_nonfoil = " non foil " in product_norm or " nonfoil " in product_norm
    product_foil = (
        " traditional foil " in product_norm
        or (" foil " in product_norm and not product_nonfoil)
    )
'''
    text = replace_once(text, old_strong, new_strong, "strong identity compact nonfoil")

    PRECISION.write_text(text, encoding="utf-8")


def append_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    marker = "def test_compact_nonfoil_canonical_rejects_rainbow_foil_listing():"
    if marker in text:
        return

    addition = r'''


def test_compact_nonfoil_canonical_rejects_rainbow_foil_listing():
    result = strict_match_listing(
        secret_lair_product("x NALAC Drop: Nuestra Magia — Nonfoil Edition"),
        listing("MTG Secret Lair x NALAC Drop Nuestra Magia Rainbow Foil Sealed"),
        "RUN",
        "2026-07-24T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_compact_nonfoil_canonical_accepts_true_nonfoil_listing():
    result = strict_match_listing(
        secret_lair_product("x NALAC Drop: Nuestra Magia — Nonfoil Edition"),
        listing("MTG Secret Lair x NALAC Drop Nuestra Magia Nonfoil Edition Sealed"),
        "RUN",
        "2026-07-24T00:00:00Z",
    )
    assert "secret_lair_variant_conflict" not in result.exclusion_reasons
'''
    TESTS.write_text(text + addition, encoding="utf-8")


def apply() -> None:
    apply_precision()
    append_tests()
    print("EBAY MATCHER COMPACT NONFOIL REPAIR: APPLIED")
    print(f"Updated: {PRECISION.relative_to(ROOT)}")
    print(f"Updated: {TESTS.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
