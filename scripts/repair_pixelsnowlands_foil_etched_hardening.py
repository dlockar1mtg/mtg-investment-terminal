from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")

OLD_RULE = '''    if " pixelsnowlands jpg " in product_norm:
        product_pixel_subtype = _secret_lair_foil_subtype(product_norm)
        title_pixel_subtype = _secret_lair_foil_subtype(title_norm)
        title_has_generic_foil = " foil " in title_norm
        if (
            product_pixel_subtype in {"traditional", "etched"}
            and title_has_generic_foil
            and title_pixel_subtype is None
        ):
            return True
'''

NEW_RULE = '''    if " pixelsnowlands jpg " in product_norm:
        product_is_etched = (
            " foil etched " in product_norm
            or " etched foil " in product_norm
        )
        product_is_traditional = " traditional foil " in product_norm
        title_has_explicit_etched = (
            " foil etched " in title_norm
            or " etched foil " in title_norm
        )
        title_has_explicit_traditional = " traditional foil " in title_norm
        title_has_generic_foil = " foil " in title_norm

        if product_is_etched and title_has_generic_foil and not title_has_explicit_etched:
            return True
        if (
            product_is_traditional
            and title_has_generic_foil
            and not title_has_explicit_traditional
        ):
            return True
'''


def apply() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")

    if NEW_RULE.strip() in precision:
        print("PIXELSNOWLANDS FOIL ETCHED REPAIR: ALREADY APPLIED")
        return

    if OLD_RULE not in precision:
        raise RuntimeError("Expected PixelSnowLands rule not found")

    precision = precision.replace(OLD_RULE, NEW_RULE, 1)
    PRECISION_PATH.write_text(precision, encoding="utf-8")

    print("PIXELSNOWLANDS FOIL ETCHED REPAIR: APPLIED")
    print(f"Matcher: {PRECISION_PATH}")
    print("Rule: generic Foil Edition cannot identify Etched or Traditional PixelSnowLands")


if __name__ == "__main__":
    apply()
