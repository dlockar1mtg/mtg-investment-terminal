from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRECISION = ROOT / "terminal2/market_sources/ebay_precision.py"
AUDIT = ROOT / "scripts/audit_ebay_matching_batch.py"
TESTS = ROOT / "tests/test_ebay_matching_precision.py"
AUDIT_TESTS = ROOT / "tests/test_ebay_audit_precision.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Expected {label} anchor not found")
    return text.replace(old, new, 1)


def apply_precision() -> None:
    text = PRECISION.read_text(encoding="utf-8")

    old_subtypes = '''def _secret_lair_foil_subtype(value_norm: str) -> str | None:
    if " double rainbow foil " in value_norm:
        return "double_rainbow"
    if " rainbow foil " in value_norm:
        return "rainbow"
    if " traditional foil " in value_norm:
        return "traditional"
    return None
'''
    new_subtypes = '''def _secret_lair_foil_subtype(value_norm: str) -> str | None:
    if " double rainbow foil " in value_norm:
        return "double_rainbow"
    if " confetti foil " in value_norm:
        return "confetti"
    if " galaxy foil " in value_norm:
        return "galaxy"
    if " raised foil " in value_norm:
        return "raised"
    if " foil etched " in value_norm or " etched foil " in value_norm:
        return "etched"
    if " rainbow foil " in value_norm:
        return "rainbow"
    if " traditional foil " in value_norm:
        return "traditional"
    return None
'''
    text = replace_once(text, old_subtypes, new_subtypes, "foil subtype")

    anchor = '''    if _secret_lair_explicit_identity_conflict(product_norm, title_norm):
        return True

'''
    insertion = '''    if _secret_lair_explicit_identity_conflict(product_norm, title_norm):
        return True

    # Furby drops share many generic tokens, so the named drop identity must agree.
    furby_identities = (
        " doo ay noo lah ",
        " the gathering ",
        " the oddbodies ",
    )
    product_furby = next(
        (identity for identity in furby_identities if identity in product_norm),
        None,
    )
    title_furby = next(
        (identity for identity in furby_identities if identity in title_norm),
        None,
    )
    if product_furby is not None and title_furby is not None and product_furby != title_furby:
        return True

    # The Last of Us Part I and Part II are distinct sealed products. Accept either
    # Roman or Arabic numbering, but require the listing's explicit part to agree.
    if " the last of us part " in product_norm:
        product_last_part = re.search(r" the last of us part (i{1,2}|1|2) ", product_norm)
        title_last_part = re.search(r" the last of us part (i{1,2}|1|2) ", title_norm)
        if product_last_part and title_last_part:
            normalize_part = {"i": "1", "ii": "2", "1": "1", "2": "2"}
            if normalize_part[product_last_part.group(1)] != normalize_part[title_last_part.group(1)]:
                return True

    # Post Malone Backstage Pass and The Lands are separate drops.
    if " post malone " in product_norm:
        product_backstage = " backstage pass " in product_norm
        product_lands = " the lands " in product_norm
        title_backstage = " backstage pass " in title_norm
        title_lands = " the lands " in title_norm
        if (product_backstage and title_lands) or (product_lands and title_backstage):
            return True

'''
    text = replace_once(text, anchor, insertion, "identity conflict")
    PRECISION.write_text(text, encoding="utf-8")


def apply_audit() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    old = '''    canonical_nonfoil = bool(re.search(r"\\bnon[- ]?foil\\b", canonical, re.IGNORECASE))
    title_nonfoil = bool(re.search(r"\\bnon[- ]?foil\\b", title, re.IGNORECASE))
    title_without_nonfoil = re.sub(r"\\bnon[- ]?foil\\b", " ", title, flags=re.IGNORECASE)
'''
    new = '''    nonfoil_pattern = r"\\bnon(?:\\s*-\\s*|\\s+)foil\\b"
    canonical_nonfoil = bool(re.search(nonfoil_pattern, canonical, re.IGNORECASE))
    title_nonfoil = bool(re.search(nonfoil_pattern, title, re.IGNORECASE))
    title_without_nonfoil = re.sub(nonfoil_pattern, " ", title, flags=re.IGNORECASE)
'''
    text = replace_once(text, old, new, "audit nonfoil regex")
    AUDIT.write_text(text, encoding="utf-8")


def append_precision_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    marker = "def test_final_batch_furby_drop_identity_conflict_is_rejected():"
    if marker in text:
        return
    addition = r'''


def secret_lair_product(name: str) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id="SL-TEST",
        canonical_product_name=name,
        canonical_set_name="Secret Lair",
        product_class="SEALED_SECRET_LAIR",
        tcgplayer_product_id="3",
        release_date="",
        ebay_query="query",
    )


def test_final_batch_furby_drop_identity_conflict_is_rejected():
    result = strict_match_listing(
        secret_lair_product("x Furby: The Gathering - Confetti Foil Edition — Foil Edition"),
        listing("MTG Secret Lair x Furby The Oddbodies Confetti Foil Edition Sealed"),
        "RUN",
        "2026-07-24T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_final_batch_furby_finish_subtype_conflict_is_rejected():
    result = strict_match_listing(
        secret_lair_product("x Furby: The Oddbodies - Confetti Foil Edition — Foil Edition"),
        listing("MTG Secret Lair x Furby The Oddbodies Rainbow Foil Edition Sealed"),
        "RUN",
        "2026-07-24T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_final_batch_last_of_us_part_identity_conflict_is_rejected():
    result = strict_match_listing(
        secret_lair_product("x The Last of Us Part I - Rainbow Foil Edition — Foil Edition"),
        listing("MTG Secret Lair x The Last of Us Part II Rainbow Foil Sealed"),
        "RUN",
        "2026-07-24T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_final_batch_last_of_us_arabic_alias_can_match():
    result = strict_match_listing(
        secret_lair_product("x The Last of Us Part I - Rainbow Foil Edition — Foil Edition"),
        listing("MTG Secret Lair x The Last of Us Part 1 Rainbow Foil Sealed"),
        "RUN",
        "2026-07-24T00:00:00Z",
    )
    assert "secret_lair_variant_conflict" not in result.exclusion_reasons


def test_final_batch_post_malone_drop_identity_conflict_is_rejected():
    result = strict_match_listing(
        secret_lair_product("x Post Malone: The Lands - Traditional Foil Edition — Foil Edition"),
        listing("MTG Secret Lair Post Malone Backstage Pass Traditional Foil Sealed"),
        "RUN",
        "2026-07-24T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
'''
    TESTS.write_text(text + addition, encoding="utf-8")


def write_audit_tests() -> None:
    content = r'''from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_ebay_matching_batch",
    ROOT / "scripts/audit_ebay_matching_batch.py",
)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def accepted_row(canonical: str, title: str) -> dict[str, str]:
    return {
        "match_state": "ACCEPTED",
        "canonical_product_name": canonical,
        "title": title,
        "exclusion_reasons": "",
        "match_score": "0.90",
    }


def test_hyphen_spaced_nonfoil_does_not_trigger_positive_foil_exception():
    reasons = AUDIT.flag_row(
        accepted_row(
            "x Warhammer Age of Sigmar - Non-Foil Edition",
            "MTG Secret Lair x Warhammer Age of Sigmar -Non- Foil Edition Sealed",
        ),
        0.82,
    )
    assert "nonfoil_canonical_with_positive_foil_title" not in reasons


def test_true_positive_foil_title_still_triggers_for_nonfoil_canonical():
    reasons = AUDIT.flag_row(
        accepted_row(
            "x NALAC Drop: Nuestra Magia — Nonfoil Edition",
            "MTG Secret Lair Nuestra Magia Rainbow Foil Sealed",
        ),
        0.82,
    )
    assert "nonfoil_canonical_with_positive_foil_title" in reasons
'''
    AUDIT_TESTS.write_text(content, encoding="utf-8")


def apply() -> None:
    apply_precision()
    apply_audit()
    append_precision_tests()
    write_audit_tests()
    print("FINAL SECRET LAIR BATCH COLLISION HARDENING: APPLIED")
    print(f"Updated: {PRECISION.relative_to(ROOT)}")
    print(f"Updated: {AUDIT.relative_to(ROOT)}")
    print(f"Updated: {TESTS.relative_to(ROOT)}")
    print(f"Created: {AUDIT_TESTS.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
