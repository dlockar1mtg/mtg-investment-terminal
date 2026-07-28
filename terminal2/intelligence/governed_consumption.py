from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ConsumptionDecision:
    forecast_consumption_state: str
    recommendation_consumption_state: str
    governed_forecast_eligible: bool
    governed_recommendation_eligible: bool
    suppression_reason: str


def yes(value: object) -> bool:
    return str(value or "").strip().upper() in {"YES", "TRUE", "1"}


def decide_consumption(
    valuation: Mapping[str, object],
    intelligence: Mapping[str, object] | None,
) -> ConsumptionDecision:
    valuation_state = str(valuation.get("valuation_state", "")).strip()
    model_eligible = yes(valuation.get("model_eligible"))
    dashboard_eligible = yes(valuation.get("dashboard_eligible"))

    if valuation_state == "VALUATION_UNAVAILABLE":
        return ConsumptionDecision(
            "SUPPRESSED_NO_DEFENSIBLE_PRICE",
            "SUPPRESSED_NO_DEFENSIBLE_PRICE",
            False,
            False,
            "GOVERNED_VALUATION_UNAVAILABLE",
        )

    if valuation_state == "CURRENT_ASKING_REFERENCE_ONLY":
        return ConsumptionDecision(
            "REFERENCE_ONLY_NOT_MODEL_ELIGIBLE",
            "WATCH_ONLY_CURRENT_ASKING_REFERENCE",
            False,
            False,
            "CURRENT_ASKING_REFERENCE_NOT_SOLD_HISTORY",
        )

    if intelligence is None:
        return ConsumptionDecision(
            "NO_LEGACY_INTELLIGENCE_MATCH",
            "NO_LEGACY_INTELLIGENCE_MATCH",
            False,
            False,
            "NO_MATCHING_CERTIFIED_INTELLIGENCE_ROW",
        )

    legacy_forecast = yes(intelligence.get("forecast_eligible"))
    legacy_recommendation = yes(intelligence.get("recommendation_eligible"))
    forecast_ok = model_eligible and legacy_forecast
    recommendation_ok = forecast_ok and legacy_recommendation

    return ConsumptionDecision(
        "ELIGIBLE" if forecast_ok else "SUPPRESSED_LEGACY_FORECAST_INELIGIBLE",
        "ELIGIBLE" if recommendation_ok else "SUPPRESSED_RECOMMENDATION_INELIGIBLE",
        forecast_ok,
        recommendation_ok,
        "" if recommendation_ok else str(
            intelligence.get("suppression_reason", "")
        ).strip() or "LEGACY_INTELLIGENCE_GUARDRAIL",
    )


def guarded_rank_score(
    current_price: object,
    three_year_base: object,
    confidence: object,
) -> float | None:
    try:
        current = float(str(current_price or "").replace(",", ""))
        future = float(str(three_year_base or "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    if current <= 0 or future <= 0:
        return None

    confidence_text = str(confidence or "").strip().upper()
    confidence_weight = {
        "HIGH": 1.0,
        "MEDIUM": 0.75,
        "LOW": 0.5,
    }.get(confidence_text)
    if confidence_weight is None:
        try:
            confidence_weight = max(
                0.0, min(1.0, float(confidence_text) / 100.0)
            )
        except ValueError:
            confidence_weight = 0.5

    three_year_return = future / current - 1.0
    return round(three_year_return * confidence_weight * 100.0, 6)
