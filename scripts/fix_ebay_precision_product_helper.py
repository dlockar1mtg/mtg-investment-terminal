from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tests" / "test_ebay_matching_precision.py"

OLD_SIGNATURE = 'def product(name: str = "Alpha Edition - Booster Box") -> CanonicalProduct:'
NEW_SIGNATURE = '''def product(
    name: str = "Alpha Edition - Booster Box",
    product_class: str = "PRE_COLLECTOR_BOOSTER_BOX",
) -> CanonicalProduct:'''


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    if NEW_SIGNATURE in text:
        print("Precision test helper is already updated.")
        return

    if OLD_SIGNATURE not in text:
        raise RuntimeError("Expected product helper signature was not found; no file was changed.")

    start = text.index(OLD_SIGNATURE)
    next_helper = text.index("\ndef collector_product", start)
    helper = text[start:next_helper]

    fixed_helper = helper.replace(OLD_SIGNATURE, NEW_SIGNATURE, 1)
    fixed_helper = fixed_helper.replace(
        '        product_class="PRE_COLLECTOR_BOOSTER_BOX",',
        "        product_class=product_class,",
        1,
    )

    if fixed_helper == helper or "product_class=product_class" not in fixed_helper:
        raise RuntimeError("The helper could not be updated safely; no file was changed.")

    TARGET.write_text(text[:start] + fixed_helper + text[next_helper:], encoding="utf-8")

    print("EBAY PRECISION PRODUCT HELPER: UPDATED")
    print(f"Target: {TARGET.relative_to(ROOT)}")
    print("Default class: PRE_COLLECTOR_BOOSTER_BOX")
    print("Optional keyword: product_class")


if __name__ == "__main__":
    main()
