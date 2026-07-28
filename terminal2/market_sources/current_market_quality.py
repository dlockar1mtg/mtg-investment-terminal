from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Sequence

NOISE = {
    "magic", "the", "gathering", "mtg", "secret", "lair", "drop",
    "standard", "edition", "foil", "nonfoil", "non", "traditional",
    "bundle", "boxed", "box", "sealed", "factory", "new", "deck",
    "commander", "superdrop", "x", "and", "with", "of", "a", "an",
}

def normalize(text: str) -> str:
    text = text.casefold().replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())

def informative_tokens(text: str) -> list[str]:
    return [
        token for token in normalize(text).split()
        if token not in NOISE and len(token) > 2
    ]

@dataclass(frozen=True)
class QualityDecision:
    identity_score: float
    matched_tokens: tuple[str, ...]
    required_tokens: tuple[str, ...]
    quality_state: str
    quality_reason: str

def evaluate_identity(
    canonical_product_name: str,
    listing_title: str,
) -> QualityDecision:
    required = tuple(dict.fromkeys(informative_tokens(canonical_product_name)))
    title_tokens = set(informative_tokens(listing_title))
    matched = tuple(token for token in required if token in title_tokens)

    if not required:
        return QualityDecision(
            0.0, matched, required, "REVIEW_REQUIRED",
            "NO_INFORMATIVE_CANONICAL_TOKENS",
        )

    score = len(matched) / len(required)
    title_norm = normalize(listing_title)
    brand_signal = (
        "magic the gathering" in title_norm
        or "mtg" in title_norm.split()
        or "secret lair" in title_norm
    )

    generic_single_tokens = {
        "full",
        "complete",
        "everything",
        "bundle",
        "standard",
        "foil",
        "nonfoil",
        "edition",
    }

    if len(required) == 1:
        approved = (
            score == 1.0
            and brand_signal
            and required[0] not in generic_single_tokens
        )
    elif len(required) == 2:
        approved = score == 1.0 and brand_signal
    else:
        approved = score >= 0.70 and len(matched) >= 2 and brand_signal

    if approved:
        state = "AUTO_APPROVED"
        reason = "IDENTITY_AND_BRAND_CONFIRMED"
    elif score >= 0.45 and matched:
        state = "REVIEW_REQUIRED"
        reason = "PARTIAL_IDENTITY_MATCH"
    else:
        state = "REJECTED_IDENTITY"
        reason = "INSUFFICIENT_IDENTITY_MATCH"

    return QualityDecision(
        round(score, 6), matched, required, state, reason
    )

def robust_snapshot(prices: Sequence[float]) -> dict[str, float]:
    clean = sorted(value for value in prices if value > 0)
    if not clean:
        return {
            "listing_count": 0,
            "minimum_price": 0.0,
            "median_price": 0.0,
            "maximum_price": 0.0,
        }
    return {
        "listing_count": len(clean),
        "minimum_price": clean[0],
        "median_price": float(median(clean)),
        "maximum_price": clean[-1],
    }
