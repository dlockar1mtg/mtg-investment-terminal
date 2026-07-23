from pathlib import Path

MATCHER = Path("terminal2/market_sources/ebay_precision.py")
TESTS = Path("tests/test_ebay_matching_precision.py")

matcher_text = MATCHER.read_text(encoding="utf-8")
test_text = TESTS.read_text(encoding="utf-8")

helper_anchor = '''def _secret_lair_foil_subtype(value_norm: str) -> str | None:
    if " double rainbow foil " in value_norm:
        return "double_rainbow"
    if " rainbow foil " in value_norm:
        return "rainbow"
    if " traditional foil " in value_norm:
        return "traditional"
    return None
'''

helper_block = helper_anchor + '''\n\ndef _secret_lair_mixed_finish_or_choice(value_norm: str) -> bool:
    choice_terms = (
        " upick ",
        " u pick ",
        " you pick ",
        " choice of ",
        " choose foil ",
        " choose non foil ",
    )
    if any(term in value_norm for term in choice_terms):
        return True

    has_nonfoil = " non foil " in value_norm or " nonfoil " in value_norm
    without_nonfoil = value_norm.replace(" non foil ", " ").replace(" nonfoil ", " ")
    has_positive_foil = " foil " in without_nonfoil
    return has_nonfoil and has_positive_foil


def _secret_lair_declares_single_finish(value_norm: str) -> bool:
    return (
        " non foil " in value_norm
        or " nonfoil " in value_norm
        or " foil " in value_norm
    )
'''

if "def _secret_lair_mixed_finish_or_choice" not in matcher_text:
    if helper_anchor not in matcher_text:
        raise SystemExit("Could not find foil subtype helper anchor")
    matcher_text = matcher_text.replace(helper_anchor, helper_block, 1)

conflict_anchor = '''    if (
        product_foil_subtype is not None
        and title_foil_subtype is not None
        and product_foil_subtype != title_foil_subtype
    ):
        return True
'''

conflict_block = conflict_anchor + '''\n    if (
        _secret_lair_declares_single_finish(product_norm)
        and _secret_lair_mixed_finish_or_choice(title_norm)
    ):
        return True
'''

if "_secret_lair_mixed_finish_or_choice(title_norm)" not in matcher_text:
    if conflict_anchor not in matcher_text:
        raise SystemExit("Could not find foil subtype conflict anchor")
    matcher_text = matcher_text.replace(conflict_anchor, conflict_block, 1)

new_tests = r'''


def test_secret_lair_nonfoil_rejects_mixed_rainbow_and_nonfoil_set_listing():
    result = strict_match_listing(
        product(
            "Drop: Artist Series: Kieran Yanner - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Artist Series Kieran Yanner Rainbow Foil Non Foil Set Sealed"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_nonfoil_rejects_combined_foil_nonfoil_listing():
    result = strict_match_listing(
        product(
            "Drop: Artist Series: Livia Prima - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Artist Series Livia Prima Non-Foil+Foil Edition Sealed"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_nonfoil_rejects_upick_finish_listing():
    result = strict_match_listing(
        product(
            "Drop: Artist Series: Ryan Alexander Lee - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Artist Series Ryan Alexander Lee Upick Foil/Non Foil SLD"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons
'''

if "test_secret_lair_nonfoil_rejects_mixed_rainbow_and_nonfoil_set_listing" not in test_text:
    test_text = test_text.rstrip() + new_tests + "\n"

MATCHER.write_text(matcher_text, encoding="utf-8")
TESTS.write_text(test_text, encoding="utf-8")

print("SECRET LAIR MIXED-FINISH HARDENING: APPLIED")
print(f"Matcher: {MATCHER}")
print(f"Tests: {TESTS}")
print("Rule: single-finish products reject mixed-finish and buyer-choice listings")
