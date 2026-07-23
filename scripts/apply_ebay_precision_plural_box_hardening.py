from __future__ import annotations

from pathlib import Path

PRECISION_PATH = Path("terminal2/market_sources/ebay_precision.py")
TEST_PATH = Path("tests/test_ebay_matching_precision.py")
CERT_PATH = Path("scripts/certify_pre_collector_booster_ebay_batches.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find expected {label} block")
    return text.replace(old, new, 1)


def main() -> None:
    precision = PRECISION_PATH.read_text(encoding="utf-8")

    precision = replace_once(
        precision,
        "def _is_incomplete_product(title_norm: str) -> bool:\n",
        "def _is_ambiguous_plural_box_listing(title_norm: str) -> bool:\n"
        "    # The pricing lane governs one complete retail box per listing.\n"
        "    # A plural form without an explicit single-unit qualifier does not\n"
        "    # establish that the observed price represents one box.\n"
        "    return (\n"
        "        \" booster boxes \" in title_norm\n"
        "        or \" booster displays \" in title_norm\n"
        "    )\n\n\n"
        "def _is_incomplete_product(title_norm: str) -> bool:\n",
        "plural-box detector insertion point",
    )

    precision = replace_once(
        precision,
        '        if _is_incomplete_product(title_norm):\n            reasons.append("incomplete_product")\n',
        '        if _is_incomplete_product(title_norm):\n            reasons.append("incomplete_product")\n'
        '        if _is_ambiguous_plural_box_listing(title_norm):\n'
        '            reasons.append("ambiguous_multi_unit_listing")\n',
        "plural-box reason application",
    )

    precision = replace_once(
        precision,
        '            "incomplete_product",\n',
        '            "incomplete_product",\n'
        '            "ambiguous_multi_unit_listing",\n',
        "plural-box hard reason",
    )

    PRECISION_PATH.write_text(precision, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    insertion = '''\n\ndef test_plural_booster_boxes_are_rejected_as_ambiguous_multi_unit():\n    result = strict_match_listing(\n        product("Amonkhet - Booster Box"),\n        listing("MtG Magic the Gathering Amonkhet Booster Boxes"),\n        "RUN",\n        "2026-07-23T00:00:00Z",\n    )\n    assert result.match_state == "REJECTED"\n    assert "ambiguous_multi_unit_listing" in result.exclusion_reasons\n'''
    marker = "\ndef test_precision_runner_uses_strict_matcher_without_recursion"
    if insertion.strip() not in tests:
        if marker not in tests:
            raise RuntimeError("Could not find test insertion point")
        tests = tests.replace(marker, insertion + marker, 1)
    TEST_PATH.write_text(tests, encoding="utf-8")

    cert = CERT_PATH.read_text(encoding="utf-8")
    if '    "ambiguous_multi_unit_listing",\n' not in cert:
        cert = replace_once(
            cert,
            '    "multi_unit_lot",\n',
            '    "multi_unit_lot",\n    "ambiguous_multi_unit_listing",\n',
            "certification hard reason",
        )
    CERT_PATH.write_text(cert, encoding="utf-8")

    print("Plural Booster Boxes hardening applied.")
    print(f"Updated: {PRECISION_PATH}")
    print(f"Updated: {TEST_PATH}")
    print(f"Updated: {CERT_PATH}")


if __name__ == "__main__":
    main()
