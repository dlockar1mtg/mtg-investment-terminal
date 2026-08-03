from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_precision_v2 import identity_match_listing as precision_v2_match_listing
from terminal2.market_sources.ebay_universal_classification import classify_listing_identity


MATCHER_VERSION = "precision-v3-universal"

_GOVERNED_PRODUCT_ALIASES: dict[str, str] = {
    # The governed name includes the franchise prefix "Universes Beyond:" while
    # marketplace titles normally begin with "Lord of the Rings" or "LOTR".
    # Removing only that nonessential prefix preserves the exact set subtitle and
    # Collector Booster display identity while avoiding false token-coverage REVIEW.
    "484912": "Lord of the Rings Tales of Middle-earth Collector Booster Display",
}


def _normalized_product_for_matching(product: base.CanonicalProduct) -> base.CanonicalProduct:
    alias = _GOVERNED_PRODUCT_ALIASES.get(str(product.tcgplayer_product_id or "").strip())
    if not alias:
        return product
    return replace(product, canonical_product_name=alias)


def identity_match_listing(
    product: base.CanonicalProduct,
    item: Mapping[str, object],
    run_id: str,
    observed: str,
) -> base.MatchResult:
    """Apply precision-v2, governed aliases, then downgrade-only universal policy."""

    matching_product = _normalized_product_for_matching(product)
    result = precision_v2_match_listing(matching_product, item, run_id, observed)
    if matching_product is not product:
        alias_reasons = [value for value in result.exclusion_reasons.split("|") if value]
        alias_reasons.append("governed_product_alias_applied")
        result = replace(
            result,
            canonical_product_name=product.canonical_product_name,
            exclusion_reasons="|".join(dict.fromkeys(alias_reasons)),
        )

    policy = classify_listing_identity(
        product.canonical_product_name,
        product.product_class,
        result.title,
    )

    reasons = [value for value in result.exclusion_reasons.split("|") if value]
    reasons.extend(policy.hard_conflicts)
    reasons.extend(policy.review_reasons)
    reasons.extend(policy.audit_tags)
    reasons.append(f"universal_policy_decision:{policy.decision.lower()}")
    reasons.append(f"universal_policy_confidence:{policy.confidence:.2f}")

    state = result.match_state
    score = result.match_score

    if policy.decision == "REJECTED":
        state = "REJECTED"
        score = min(score, 0.49)
    elif policy.decision == "REVIEW" and state == "ACCEPTED":
        state = "REVIEW"
        score = min(score, 0.75)

    return replace(
        result,
        canonical_product_name=product.canonical_product_name,
        match_state=state,
        match_score=round(score, 4),
        exclusion_reasons="|".join(dict.fromkeys(reasons)),
    )
