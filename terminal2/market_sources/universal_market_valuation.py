from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping


@dataclass(frozen=True)
class ValuationDecision:
    selected_reference_price: float | None
    selected_reference_date: str
    selected_source_type: str
    valuation_state: str
    model_eligible: bool
    dashboard_eligible: bool
    freshness_days: int | None
    freshness_state: str
    valuation_reason: str


def parse_positive(value: object) -> float | None:
    try:
        parsed = float(str(value or "").replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def parse_date(value: object) -> date | None:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def freshness_days(observation_date: object, as_of: date) -> int | None:
    parsed = parse_date(observation_date)
    if parsed is None:
        return None
    return max(0, (as_of - parsed).days)


def freshness_state(days: int | None) -> str:
    if days is None:
        return "DATE_UNAVAILABLE"
    if days <= 7:
        return "FRESH_0_TO_7_DAYS"
    if days <= 30:
        return "CURRENT_8_TO_30_DAYS"
    if days <= 90:
        return "AGING_31_TO_90_DAYS"
    if days <= 365:
        return "STALE_91_TO_365_DAYS"
    return "HISTORICAL_OVER_365_DAYS"


def choose_valuation(
    history_row: Mapping[str, object] | None,
    asking_row: Mapping[str, object] | None,
    as_of: date,
) -> ValuationDecision:
    history_price = parse_positive(
        history_row.get("consolidated_market_price")
        if history_row else None
    )
    asking_price = parse_positive(
        asking_row.get("median_price")
        if asking_row else None
    )

    if history_price is not None:
        selected_date = str(history_row.get("observation_date", ""))[:10]
        days = freshness_days(selected_date, as_of)
        return ValuationDecision(
            selected_reference_price=history_price,
            selected_reference_date=selected_date,
            selected_source_type="DIRECT_HISTORICAL_MARKET",
            valuation_state="DIRECT_HISTORY_VALUATION",
            model_eligible=True,
            dashboard_eligible=True,
            freshness_days=days,
            freshness_state=freshness_state(days),
            valuation_reason="LATEST_CONSOLIDATED_DIRECT_HISTORY",
        )

    if asking_price is not None:
        selected_date = str(asking_row.get("observation_date", ""))[:10]
        days = freshness_days(selected_date, as_of)
        return ValuationDecision(
            selected_reference_price=asking_price,
            selected_reference_date=selected_date,
            selected_source_type="CURRENT_ASKING_REFERENCE",
            valuation_state="CURRENT_ASKING_REFERENCE_ONLY",
            model_eligible=False,
            dashboard_eligible=True,
            freshness_days=days,
            freshness_state=freshness_state(days),
            valuation_reason=(
                "NO_DIRECT_HISTORY_QUALITY_APPROVED_CURRENT_ASKING_MEDIAN"
            ),
        )

    return ValuationDecision(
        selected_reference_price=None,
        selected_reference_date="",
        selected_source_type="NO_DEFENSIBLE_PRICE",
        valuation_state="VALUATION_UNAVAILABLE",
        model_eligible=False,
        dashboard_eligible=False,
        freshness_days=None,
        freshness_state="DATE_UNAVAILABLE",
        valuation_reason="NO_DIRECT_HISTORY_OR_APPROVED_CURRENT_ASKING_PRICE",
    )
