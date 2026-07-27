from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_precision_v2 import identity_match_listing as precision_v2_match_listing
from terminal2.market_sources.ebay_universal_classification import classify_listing_identity


MATCHER_VERSION = "precision-v3-universal"


def identity_match_listing(
    product: base.CanonicalProduct,
    item: Mapping[str, object],
    run_id: str,
    observed: str,
) -> base.MatchResult:
    """Apply the certified precision-v2 matcher, then a downgrade-only universal policy.

    The universal layer never upgrades a precision-v2 result. It adds normalized
    language, form, condition, completeness, and quantity diagnostics and only
    downgrades when the listing contains an explicit conflict or material missing
    qualifier.
    """

    result = precision_v2_match_listing(product, item, run_id, observed)
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
        match_state=state,
        match_score=round(score, 4),
        exclusion_reasons="|".join(dict.fromkeys(reasons)),
    )
