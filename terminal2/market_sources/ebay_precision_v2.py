from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_precision import strict_match_listing
from terminal2.market_sources.ebay_product_identity import evaluate_title, parse_product_identity


def identity_match_listing(
    product: base.CanonicalProduct,
    item: Mapping[str, object],
    run_id: str,
    observed: str,
) -> base.MatchResult:
    result = strict_match_listing(product, item, run_id, observed)
    identity = parse_product_identity(product.canonical_product_name, product.product_class)
    identity_ok, identity_reasons, coverage = evaluate_title(identity, result.title)

    reasons = [value for value in result.exclusion_reasons.split("|") if value]
    reasons.extend(identity_reasons)
    score = result.match_score
    state = result.match_state

    if not identity_ok:
        hard_conflict = any(
            reason.startswith("forbidden_phrase:")
            or reason.startswith("missing_required_phrase:")
            for reason in identity_reasons
        )
        if hard_conflict:
            score = min(score, 0.49)
            state = "REJECTED"
        elif state == "ACCEPTED":
            score = min(score, 0.75)
            state = "REVIEW"
    elif state == "ACCEPTED" and coverage < 0.85:
        reasons.append("identity_coverage_below_accept_threshold")
        score = min(score, 0.75)
        state = "REVIEW"

    reasons.extend((
        f"identity_family:{identity.product_family.lower()}",
        f"identity_form:{identity.product_form.lower()}",
        f"identity_finish:{identity.finish.lower()}",
    ))
    return replace(
        result,
        match_score=round(score, 4),
        match_state=state,
        exclusion_reasons="|".join(dict.fromkeys(reasons)),
    )
