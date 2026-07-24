from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find expected {label} block")
    return text.replace(old, new, 1)


def main() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")

    old = '''    if re.search(r"\\bbooster\\s+boxes?\\b.*\\bbooster\\s+boxes?\\b", title_norm):
        return True
'''
    new = '''    # A title such as "Journey into Nyx & Origins Booster Boxes" names
    # two products but contains the product-form phrase only once.  Detect the
    # connector plus a plural box form instead of requiring two repetitions of
    # "booster box".
    if (
        (" & " in raw_title or " and " in raw_lower)
        and " booster boxes " in title_norm
    ):
        return True

    if re.search(r"\\bbooster\\s+boxes?\\b.*\\bbooster\\s+boxes?\\b", title_norm):
        return True
'''

    precision = replace_once(
        precision,
        old,
        new,
        "ampersand multi-product detector",
    )

    PRECISION_PATH.write_text(precision, encoding="utf-8")
    print("Ampersand multi-product eBay detection fixed.")
    print(f"Updated: {PRECISION_PATH}")


if __name__ == "__main__":
    main()
