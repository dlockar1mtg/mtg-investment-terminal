from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from terminal2.market_sources import ebay_matching as base


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


def strict_match_listing(
    product: base.CanonicalProduct,
    item: Mapping[str, object],
    run_id: str,
    observed: str,
) -> base.MatchResult:
    result = base.match_listing(product, item, run_id, observed)
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
        if token_coverage < 0.75:
            reasons.append("insufficient_product_identity")

        hard_reasons = {
            "unrelated_game",
            "missing_mtg_identity",
            "missing_booster_box_form",
            "excluded_product_form",
            "loose_packs",
            "insufficient_product_identity",
            "non_english",
            "presale",
        }
        if hard_reasons.intersection(reasons):
            score = min(score, 0.49)
            state = "REJECTED"

    return replace(
        result,
        match_score=round(score, 4),
        match_state=state,
        exclusion_reasons="|".join(dict.fromkeys(reasons)),
    )


def run_coverage(
    limit_per_product: int = 20,
    max_products: int | None = None,
) -> dict[str, object]:
    original = base.match_listing
    base.match_listing = strict_match_listing
    try:
        return base.run_coverage(limit_per_product, max_products)
    finally:
        base.match_listing = original
