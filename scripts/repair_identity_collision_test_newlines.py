from __future__ import annotations

from pathlib import Path


TEST_PATH = Path("tests/test_ebay_matching_precision.py")
MARKER = r"\n\ndef test_secret_lair_cats_dogs_title_collision_is_rejected():"


def apply() -> None:
    text = TEST_PATH.read_text(encoding="utf-8")
    marker_index = text.find(MARKER)

    if marker_index == -1:
        if "def test_secret_lair_cats_dogs_title_collision_is_rejected():" in text:
            print("IDENTITY COLLISION TEST NEWLINE REPAIR: ALREADY CLEAN")
            return
        raise RuntimeError("Malformed identity-collision test block was not found")

    prefix = text[:marker_index]
    malformed_suffix = text[marker_index:]
    repaired_suffix = malformed_suffix.replace(r"\n", "\n")

    TEST_PATH.write_text(prefix + repaired_suffix, encoding="utf-8")

    print("IDENTITY COLLISION TEST NEWLINE REPAIR: APPLIED")
    print(f"Tests: {TEST_PATH}")


if __name__ == "__main__":
    apply()
