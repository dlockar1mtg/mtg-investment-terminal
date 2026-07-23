from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHER = ROOT / "terminal2/market_sources/ebay_matching.py"
TESTS = ROOT / "tests/test_ebay_matching_precision.py"

OLD_TERMS = 'PRESALE_TERMS = (" presale ", " pre sale ", " preorder ", " pre order ")'
NEW_TERMS = (
    'PRESALE_TERMS = ('
    '" presale ", " pre sale ", " presell ", " pre sell ", '
    '" preorder ", " pre order ", " pre aug ")'
)

TEST_NAME = "test_secret_lair_presell_listing_is_rejected"
TEST_BLOCK = '''\n\ndef test_secret_lair_presell_listing_is_rejected():\n    result = strict_match_listing(\n        product(\n            "Reality Fracture - Secret Lair Bundle",\n            product_class="SEALED_SECRET_LAIR",\n        ),\n        listing(\n            "Magic The Gathering Reality Fracture Secret Lair Bundle "\n            "(Presell) English Factory Sealed"\n        ),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "presale" in result.exclusion_reasons\n'''


def main() -> None:
    matcher_text = MATCHER.read_text(encoding="utf-8")
    if NEW_TERMS not in matcher_text:
        if OLD_TERMS not in matcher_text:
            raise RuntimeError("Could not locate the supported PRESALE_TERMS definition")
        matcher_text = matcher_text.replace(OLD_TERMS, NEW_TERMS, 1)
        MATCHER.write_text(matcher_text, encoding="utf-8")

    test_text = TESTS.read_text(encoding="utf-8")
    if TEST_NAME not in test_text:
        TESTS.write_text(test_text.rstrip() + TEST_BLOCK + "\n", encoding="utf-8")

    print("EBAY PRESELL EXCLUSION: APPLIED")
    print(f"Matcher: {MATCHER.relative_to(ROOT)}")
    print(f"Tests: {TESTS.relative_to(ROOT)}")
    print("Added terms: presell, pre sell, pre aug")


if __name__ == "__main__":
    main()
