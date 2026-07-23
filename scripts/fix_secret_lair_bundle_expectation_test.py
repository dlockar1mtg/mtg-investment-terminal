from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tests/test_ebay_matching_precision.py"

OLD = '''def test_secret_lair_exact_astrology_variant_can_be_accepted():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Drop Astrology Lands Aquarius Traditional Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "ACCEPTED"
'''

NEW = '''def test_secret_lair_bundle_without_bundle_identity_is_rejected():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Drop Astrology Lands Aquarius Traditional Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_exact_astrology_bundle_variant_can_be_accepted():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Drop Astrology Lands Aquarius Bundle Traditional Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "ACCEPTED"
'''


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    if NEW in text:
        print("SECRET LAIR BUNDLE EXPECTATION TEST: ALREADY UPDATED")
        return
    if OLD not in text:
        raise RuntimeError("Expected outdated Astrology bundle test block was not found")
    TARGET.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("SECRET LAIR BUNDLE EXPECTATION TEST: UPDATED")
    print(f"Target: {TARGET.relative_to(ROOT)}")
    print("Added: missing-bundle rejection and exact-bundle acceptance")


if __name__ == "__main__":
    main()
