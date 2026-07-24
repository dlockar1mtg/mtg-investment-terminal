from __future__ import annotations

from pathlib import Path

TEST_PATH = Path("tests/test_ebay_matching_precision.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find expected {label} block")
    return text.replace(old, new, 1)


def main() -> None:
    tests = TEST_PATH.read_text(encoding="utf-8")

    helper = '''\n\ndef secret_lair_product(name: str) -> CanonicalProduct:\n    return CanonicalProduct(\n        canonical_product_id="MTG-SECRET-LAIR-TEST",\n        canonical_product_name=name,\n        canonical_set_name="Secret Lair Drop Series",\n        product_class="SEALED_SECRET_LAIR",\n        tcgplayer_product_id="3",\n        release_date="2025-01-01",\n        ebay_query="query",\n    )\n'''

    marker = '\n\ndef listing(title: str) -> dict[str, object]:\n'
    if 'def secret_lair_product(' not in tests:
        if marker not in tests:
            raise RuntimeError("Could not find Secret Lair helper insertion point")
        tests = tests.replace(marker, helper + marker, 1)

    tests = tests.replace(
        'product(\n            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Non-Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        )',
        'secret_lair_product(\n            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Non-Foil Edition"\n        )',
    )
    tests = tests.replace(
        'product(\n            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",\n            product_class="SEALED_SECRET_LAIR",\n        )',
        'secret_lair_product(\n            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition"\n        )',
    )
    tests = tests.replace(
        'product(\n            "Secret Lair Countdown Kit: An Encyclopedia of Magic Book Club Bundle",\n            product_class="SEALED_SECRET_LAIR",\n        )',
        'secret_lair_product(\n            "Secret Lair Countdown Kit: An Encyclopedia of Magic Book Club Bundle"\n        )',
    )

    if 'product_class="SEALED_SECRET_LAIR"' in tests:
        raise RuntimeError("One or more unsupported product_class keyword calls remain")

    TEST_PATH.write_text(tests, encoding="utf-8")
    print("Secret Lair test product helper fixed.")
    print(f"Updated: {TEST_PATH}")


if __name__ == "__main__":
    main()
