from __future__ import annotations

import re
from dataclasses import replace
from typing import Mapping, Sequence

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_universe import build_complete_universe


ORIGINAL_MATCH_LISTING = base.match_listing
ORIGINAL_BUILD_UNIVERSE = base.build_universe

MTG_IDENTITY_TERMS = (
    " magic ",
    " mtg ",
    " wotc ",
    " wizards of the coast ",
)

UNRELATED_GAME_TERMS = (
    " sorcery contested realm ",
    " flesh and blood ",
    " alpha clash ",
    " life tcg ",
    " pokemon ",
    " yugioh ",
    " yu gi oh ",
    " battle arena ",
)

NON_BOX_PRODUCT_TERMS = (
    " starter set ",
    " starter deck ",
    " blaster box ",
    " fat pack ",
    " gift pack ",
    " bundle ",
    " booster lot ",
    " lot of packs ",
    " empty box ",
    " box topper only ",
    " wrapper ",
    " resealed ",
    " re sealed ",
    " not factory sealed ",
    " tournament pack ",
    " tournament display ",
    " theme booster ",
    " set booster ",
)

DAMAGED_SEAL_TERMS = (
    " wrap damage ",
    " wrapper damage ",
    " seal weak ",
    " weak seal ",
    " seal torn ",
    " torn seal ",
    " shrink damage ",
    " damaged wrap ",
    " box damage ",
    " damaged box ",
    " crushed box ",
    " dented box ",
)


def _has_booster_box_form(title_norm: str) -> bool:
    return any(
        phrase in title_norm
        for phrase in (
            " booster box ",
            " booster boxes ",
            " booster display ",
            " booster displays ",
            " display box ",
        )
    )


def _token_coverage(product: base.CanonicalProduct, title_norm: str) -> float:
    required = base._tokens(product.canonical_product_name)
    if not required:
        return 1.0
    present = {token for token in required if f" {token} " in title_norm}
    return len(present) / len(required)


def _is_multi_box_case(title_norm: str) -> bool:
    if " acrylic case " in title_norm or " protective case " in title_norm:
        return False
    return any(
        phrase in title_norm
        for phrase in (
            " case of ",
            " sealed case ",
            " master case ",
            " booster box case ",
            " collector case ",
            " case 6 ",
            " 6 sealed booster boxes ",
            " 6 booster boxes ",
            " six sealed booster boxes ",
            " six booster boxes ",
        )
    )


def _is_multi_unit_lot(title_norm: str) -> bool:
    patterns = (
        r"\blot\s+of\s+(?:two|2|three|3|four|4|five|5|six|6)\b",
        r"\b(?:two|2|three|3|four|4|five|5|six|6)\s+(?:sealed\s+)?(?:collector\s+)?booster\s+(?:boxes|displays)\b",
        r"\b(?:x|qty)\s*(?:2|3|4|5|6)\b.*\bbooster\s+(?:box|display)",
    )
    return any(re.search(pattern, title_norm) for pattern in patterns)


def _is_incomplete_pack_box_lot(title_norm: str) -> bool:
    patterns = (
        r"\blot\s+of\s+\d+\s+packs?\s+(?:(?:and|with)\s+)?(?:the\s+)?box\b",
        r"\b\d+\s+packs?\s+(?:(?:and|with)\s+)?(?:the\s+)?box\b",
        r"\bbox\s+(?:(?:and|with)\s+)?\d+\s+packs?\b",
    )
    return any(re.search(pattern, title_norm) for pattern in patterns)


def _is_incomplete_product(title_norm: str) -> bool:
    return any(
        phrase in title_norm
        for phrase in (
            " partial booster box ",
            " partial box ",
            " incomplete booster box ",
            " incomplete box ",
            " packs missing ",
            " missing packs ",
        )
    )


def _is_deprecated_catalog_placeholder(title_norm: str) -> bool:
    return any(
        phrase in title_norm
        for phrase in (
            " deprecated ",
            " catalog image ",
            " placeholder ",
            " stock listing only ",
        )
    )


def _is_mixed_product_listing(
    product: base.CanonicalProduct,
    title_norm: str,
    raw_title: str,
) -> bool:
    raw_lower = raw_title.lower()
    if "+" not in raw_title and " plus " not in raw_lower:
        return False

    product_name_norm = base._norm(product.canonical_product_name)
    known_other_products = (
        " collector booster ",
        " commander deck ",
        " theme deck ",
        " starter deck ",
        " fat pack ",
        " bundle ",
    )
    if not any(term in title_norm for term in known_other_products):
        return False

    if (
        product.product_class == "COLLECTOR_BOOSTER_BOX"
        and " collector booster " in product_name_norm
        and not any(
            term in title_norm
            for term in known_other_products
            if term != " collector booster "
        )
    ):
        return False
    return True


def _is_ambiguous_display_case(title_norm: str) -> bool:
    if " acrylic case " in title_norm or " protective case " in title_norm:
        return False
    return " display case " in title_norm


def _is_single_pack_collector_product(title_norm: str) -> bool:
    if " omega booster box " in title_norm or " omega box " in title_norm:
        return True
    return bool(
        re.search(
            r"\b(?:one|1)\s+(?:\d+\s*card\s+)?pack\b",
            title_norm,
        )
    )


def _has_conflicting_set_identity(
    product: base.CanonicalProduct,
    title_norm: str,
) -> bool:
    product_name = base._norm(product.canonical_product_name)

    if (
        " commander legends " in product_name
        and " battle for baldur s gate " not in product_name
        and " battle for baldur s gate " in title_norm
    ):
        return True

    if product_name.strip() == "dominaria booster box":
        return any(
            phrase in title_norm
            for phrase in (
                " dominaria remastered ",
                " dominaria united ",
            )
        )

    return False


def strict_match_listing(
    product: base.CanonicalProduct,
    item: Mapping[str, object],
    run_id: str,
    observed: str,
) -> base.MatchResult:
    result = ORIGINAL_MATCH_LISTING(product, item, run_id, observed)
    title_norm = base._norm(result.title)
    reasons = [value for value in result.exclusion_reasons.split("|") if value]
    score = result.match_score
    state = result.match_state

    if product.product_class in {
        "COLLECTOR_BOOSTER_BOX",
        "PRE_COLLECTOR_BOOSTER_BOX",
    }:
        has_mtg_identity = any(term in title_norm for term in MTG_IDENTITY_TERMS)
        unrelated_game = any(term in title_norm for term in UNRELATED_GAME_TERMS)
        has_box_form = _has_booster_box_form(title_norm)
        token_coverage = _token_coverage(product, title_norm)

        if unrelated_game:
            reasons.append("unrelated_game")
        if not has_mtg_identity:
            reasons.append("missing_mtg_identity")
        if not has_box_form:
            reasons.append("missing_booster_box_form")
        if any(term in title_norm for term in NON_BOX_PRODUCT_TERMS):
            reasons.append("excluded_product_form")
        if not has_box_form and (" pack " in title_norm or " packs " in title_norm):
            reasons.append("loose_packs")
        if _is_multi_box_case(title_norm):
            reasons.append("multi_box_case")
        if _is_multi_unit_lot(title_norm):
            reasons.append("multi_unit_lot")
        if _is_incomplete_pack_box_lot(title_norm):
            reasons.append("incomplete_pack_box_lot")
        if _is_incomplete_product(title_norm):
            reasons.append("incomplete_product")
        if _is_deprecated_catalog_placeholder(title_norm):
            reasons.append("deprecated_catalog_placeholder")
        if _is_mixed_product_listing(product, title_norm, result.title):
            reasons.append("mixed_product_listing")
        if any(term in title_norm for term in DAMAGED_SEAL_TERMS):
            reasons.append("damaged_or_uncertain_seal")
        if (
            product.product_class == "COLLECTOR_BOOSTER_BOX"
            and _is_single_pack_collector_product(title_norm)
        ):
            reasons.append("single_pack_collector_product")
        if _has_conflicting_set_identity(product, title_norm):
            reasons.append("conflicting_set_identity")
        if token_coverage < 0.75:
            reasons.append("insufficient_product_identity")

        hard_reasons = {
            "unrelated_game",
            "missing_mtg_identity",
            "missing_booster_box_form",
            "excluded_product_form",
            "loose_packs",
            "multi_box_case",
            "multi_unit_lot",
            "incomplete_pack_box_lot",
            "incomplete_product",
            "deprecated_catalog_placeholder",
            "mixed_product_listing",
            "damaged_or_uncertain_seal",
            "single_pack_collector_product",
            "conflicting_set_identity",
            "insufficient_product_identity",
            "non_english",
            "presale",
        }
        if hard_reasons.intersection(reasons):
            score = min(score, 0.49)
            state = "REJECTED"
        elif _is_ambiguous_display_case(title_norm):
            reasons.append("ambiguous_display_case")
            score = min(score, 0.75)
            state = "REVIEW"

    return replace(
        result,
        match_score=round(score, 4),
        match_state=state,
        exclusion_reasons="|".join(dict.fromkeys(reasons)),
    )


def run_coverage(
    limit_per_product: int = 20,
    max_products: int | None = None,
    universe_override: Sequence[base.CanonicalProduct] | None = None,
) -> dict[str, object]:
    original_match = base.match_listing
    original_universe = base.build_universe
    selected_universe = (
        list(universe_override)
        if universe_override is not None
        else build_complete_universe()
    )
    base.match_listing = strict_match_listing
    base.build_universe = lambda: list(selected_universe)
    try:
        return base.run_coverage(limit_per_product, max_products)
    finally:
        base.match_listing = original_match
        base.build_universe = original_universe
