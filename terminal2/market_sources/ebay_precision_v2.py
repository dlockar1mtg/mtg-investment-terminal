from __future__ import annotations

import re
from dataclasses import replace
from typing import Mapping

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources import ebay_precision as precision
from terminal2.market_sources.ebay_precision import strict_match_listing
from terminal2.market_sources.ebay_product_identity import evaluate_title, parse_product_identity


_RETAIL_PACK_COUNT = re.compile(
    r"\b(?:booster\s+(?:box|display)|display\s+box)\b.*\b(?:4|12|24|30|36)\s+packs?\b"
)
_EXPLICIT_PACK_PLUS_BOX_LOT = re.compile(
    r"\b(?:lot\s+of\s+)?\d+\s+packs?\s+(?:plus|and|with)\s+(?:the\s+)?box\b"
)
_INCOMPLETE_MARKERS = (
    " lot of ",
    " partial ",
    " incomplete ",
    " packs missing ",
    " missing packs ",
    " single pack ",
    " loose pack ",
    " one 15 card pack ",
    " 1 pack ",
    " omega box ",
    " omega booster box ",
)


def _is_complete_retail_pack_count(product: base.CanonicalProduct, title: str) -> bool:
    if "BOOSTER" not in product.product_class.upper():
        return False
    title_norm = base._norm(title)
    if _EXPLICIT_PACK_PLUS_BOX_LOT.search(title_norm):
        return False
    if any(marker in title_norm for marker in _INCOMPLETE_MARKERS):
        return False
    return bool(_RETAIL_PACK_COUNT.search(title_norm))


def _enforce_explicit_pack_plus_box_lot(result: base.MatchResult) -> base.MatchResult:
    title_norm = base._norm(result.title)
    if not _EXPLICIT_PACK_PLUS_BOX_LOT.search(title_norm):
        return result
    reasons = [value for value in result.exclusion_reasons.split("|") if value]
    reasons.append("incomplete_pack_box_lot")
    return replace(
        result,
        match_score=min(result.match_score, 0.49),
        match_state="REJECTED",
        exclusion_reasons="|".join(dict.fromkeys(reasons)),
    )


def _repair_retail_pack_count_false_rejection(
    product: base.CanonicalProduct,
    item: Mapping[str, object],
    run_id: str,
    observed: str,
    result: base.MatchResult,
) -> base.MatchResult:
    reasons = [value for value in result.exclusion_reasons.split("|") if value]
    if "incomplete_pack_box_lot" not in reasons:
        return result
    if not _is_complete_retail_pack_count(product, result.title):
        return result

    repaired_reasons = [value for value in reasons if value != "incomplete_pack_box_lot"]
    baseline = precision.ORIGINAL_MATCH_LISTING(product, item, run_id, observed)
    baseline_reasons = [value for value in baseline.exclusion_reasons.split("|") if value]

    # Restore the baseline classification only when the false incomplete-lot
    # reason was the strict layer's sole additional hard rejection.
    strict_only_reasons = [value for value in repaired_reasons if value not in baseline_reasons]
    if strict_only_reasons:
        return replace(result, exclusion_reasons="|".join(dict.fromkeys(repaired_reasons)))

    return replace(
        result,
        match_score=baseline.match_score,
        match_state=baseline.match_state,
        exclusion_reasons="|".join(dict.fromkeys(baseline_reasons)),
    )


def _repair_missing_only_secret_lair_conflict(
    product: base.CanonicalProduct,
    result: base.MatchResult,
    reasons: list[str],
    identity_reasons: list[str],
) -> tuple[str, float, list[str]]:
    state = result.match_state
    score = result.match_score
    if product.product_class != "SEALED_SECRET_LAIR":
        return state, score, reasons
    if "secret_lair_variant_conflict" not in reasons:
        return state, score, reasons

    explicit_conflict = any(
        reason.startswith("forbidden_phrase:")
        for reason in identity_reasons
    )
    missing_qualifier = any(
        reason.startswith("missing_required_phrase:")
        for reason in identity_reasons
    )
    if explicit_conflict or not missing_qualifier:
        return state, score, reasons

    # The legacy strict matcher treats an omitted bundle/finish qualifier as a
    # variant contradiction. Repair only when no independent hard-failure reason
    # remains. Explicit sibling, finish, mixed-product, and form conflicts stay
    # rejected.
    uncertainty_reasons = {
        "secret_lair_variant_conflict",
        "insufficient_product_identity",
        "insufficient_identity_token_coverage",
    }
    has_independent_hard_reason = any(
        reason not in uncertainty_reasons
        and not reason.startswith("missing_required_phrase:")
        for reason in reasons
    )
    if has_independent_hard_reason:
        return state, score, reasons

    repaired = [reason for reason in reasons if reason != "secret_lair_variant_conflict"]
    repaired.extend((
        "missing_identity_qualifier_requires_review",
        "legacy_variant_conflict_repaired_to_review",
    ))
    return "REVIEW", min(score if score > 0 else 0.75, 0.75), list(dict.fromkeys(repaired))


def identity_match_listing(
    product: base.CanonicalProduct,
    item: Mapping[str, object],
    run_id: str,
    observed: str,
) -> base.MatchResult:
    result = strict_match_listing(product, item, run_id, observed)
    result = _enforce_explicit_pack_plus_box_lot(result)
    result = _repair_retail_pack_count_false_rejection(product, item, run_id, observed, result)

    identity = parse_product_identity(product.canonical_product_name, product.product_class)
    identity_ok, identity_reasons, coverage = evaluate_title(identity, result.title)

    reasons = [value for value in result.exclusion_reasons.split("|") if value]
    reasons.extend(identity_reasons)
    score = result.match_score
    state = result.match_state

    if not identity_ok:
        explicit_conflict = any(
            reason.startswith("forbidden_phrase:")
            for reason in identity_reasons
        )
        missing_qualifier = any(
            reason.startswith("missing_required_phrase:")
            for reason in identity_reasons
        )

        if explicit_conflict:
            score = min(score, 0.49)
            state = "REJECTED"
        elif missing_qualifier:
            state, score, reasons = _repair_missing_only_secret_lair_conflict(
                product,
                result,
                reasons,
                identity_reasons,
            )
            reasons.append("missing_identity_qualifier_requires_review")
            if state == "ACCEPTED":
                score = min(score, 0.75)
                state = "REVIEW"
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
