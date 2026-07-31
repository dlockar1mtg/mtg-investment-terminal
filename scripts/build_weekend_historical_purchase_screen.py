from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

HISTORY = (
    ROOT
    / "artifacts"
    / "weekend_readiness"
    / "20260730-163101"
    / "historical_purchase_screen"
    / "25_trusted_canonical_daily_history.csv"
)

COVERAGE = (
    ROOT
    / "data"
    / "operations"
    / "mtg_universal_history_ledger"
    / "universal_mtg_history_completion_status.csv"
)

INTERFACE = (
    ROOT
    / "data"
    / "operations"
    / "mtg_terminal_delivery"
    / "latest"
    / "universal_mtg_consumption_interface.csv"
)

OUTPUT = (
    ROOT
    / "artifacts"
    / "weekend_readiness"
    / "20260730-163101"
    / "historical_purchase_screen"
)

AS_OF_DATE = date(2026, 7, 30)

MIN_PRICE = 1.00
MAX_PRICE = 100_000.00

MIN_LONG_HISTORY_DAYS = 730
MIN_MEDIUM_HISTORY_DAYS = 365
MIN_LONG_HISTORY_DATES = 18
MIN_MEDIUM_HISTORY_DATES = 8

FRESH_DAYS = 45
STALE_DAYS = 120


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None

    try:
        parsed = float(text)
    except ValueError:
        return None

    if not math.isfinite(parsed):
        return None

    return parsed


def integer(value: Any) -> int:
    parsed = number(value)
    if parsed is None:
        return 0
    return int(parsed)


def parse_date(value: Any) -> date | None:
    text = clean(value)[:10]
    if not text:
        return None

    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if fields is None:
        fields = list(rows[0].keys()) if rows else []

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def pct_change(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start <= 0:
        return None
    return ((end / start) - 1.0) * 100.0


def annualized_return(
    start: float | None,
    end: float | None,
    span_days: int,
) -> float | None:
    if (
        start is None
        or end is None
        or start <= 0
        or end <= 0
        or span_days < 180
    ):
        return None

    years = span_days / 365.25
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


def nearest_prior_price(
    observations: list[tuple[date, float]],
    target: date,
) -> tuple[date, float] | None:
    eligible = [item for item in observations if item[0] <= target]
    if not eligible:
        return None
    return max(eligible, key=lambda item: item[0])


def monthly_series(
    observations: list[tuple[date, float]],
) -> list[tuple[date, float]]:
    latest_by_month: dict[tuple[int, int], tuple[date, float]] = {}

    for observed_date, price in observations:
        key = (observed_date.year, observed_date.month)
        prior = latest_by_month.get(key)

        if prior is None or observed_date > prior[0]:
            latest_by_month[key] = (observed_date, price)

    return sorted(latest_by_month.values(), key=lambda item: item[0])


def monthly_returns(
    observations: list[tuple[date, float]],
) -> list[float]:
    monthly = monthly_series(observations)
    returns: list[float] = []

    for index in range(1, len(monthly)):
        prior = monthly[index - 1][1]
        current = monthly[index][1]

        if prior > 0 and current > 0:
            returns.append((current / prior) - 1.0)

    return returns


def annualized_volatility(
    observations: list[tuple[date, float]],
) -> float | None:
    returns = monthly_returns(observations)

    if len(returns) < 3:
        return None

    return statistics.stdev(returns) * math.sqrt(12.0) * 100.0


def maximum_drawdown(
    observations: list[tuple[date, float]],
) -> float | None:
    if not observations:
        return None

    peak = observations[0][1]
    maximum = 0.0

    for _, price in observations:
        peak = max(peak, price)

        if peak > 0:
            drawdown = ((price / peak) - 1.0) * 100.0
            maximum = min(maximum, drawdown)

    return maximum


def round_or_blank(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def classify_history(
    distinct_dates: int,
    span_days: int,
) -> str:
    if (
        distinct_dates >= MIN_LONG_HISTORY_DATES
        and span_days >= MIN_LONG_HISTORY_DAYS
    ):
        return "LONG_HISTORY"

    if (
        distinct_dates >= MIN_MEDIUM_HISTORY_DATES
        and span_days >= MIN_MEDIUM_HISTORY_DAYS
    ):
        return "MEDIUM_HISTORY"

    if distinct_dates >= 3 and span_days >= 60:
        return "SHORT_HISTORY"

    if distinct_dates >= 2:
        return "MINIMAL_HISTORY"

    if distinct_dates == 1:
        return "SINGLE_DATE"

    return "NO_HISTORY"


def freshness_state(days: int | None) -> str:
    if days is None:
        return "UNKNOWN"

    if days <= FRESH_DAYS:
        return "FRESH"

    if days <= STALE_DAYS:
        return "AGING"

    return "STALE"


def quality_penalty(
    quality: str,
    admission: str,
) -> float:
    penalty = 0.0

    if quality == "REVIEW_REQUIRED":
        penalty += 25.0
    elif quality == "EXCLUDE_FROM_MODEL":
        penalty += 60.0

    if admission == "PROVISIONAL_MODEL":
        penalty += 10.0
    elif admission == "STRUCTURAL_ONLY":
        penalty += 40.0

    return penalty


def calculate_score(
    *,
    history_class: str,
    total_return: float | None,
    cagr: float | None,
    return_365d: float | None,
    volatility: float | None,
    drawdown: float | None,
    freshness: str,
    quality: str,
    admission: str,
) -> float:
    score = 0.0

    history_points = {
        "LONG_HISTORY": 25.0,
        "MEDIUM_HISTORY": 18.0,
        "SHORT_HISTORY": 10.0,
        "MINIMAL_HISTORY": 3.0,
        "SINGLE_DATE": 0.0,
        "NO_HISTORY": 0.0,
    }
    score += history_points.get(history_class, 0.0)

    if cagr is not None:
        score += max(-15.0, min(25.0, cagr))

    if return_365d is not None:
        score += max(-10.0, min(15.0, return_365d / 2.0))

    if total_return is not None and total_return > 0:
        score += min(10.0, total_return / 10.0)

    if volatility is not None:
        if volatility <= 20:
            score += 10.0
        elif volatility <= 40:
            score += 5.0
        elif volatility >= 80:
            score -= 10.0

    if drawdown is not None:
        if drawdown >= -15:
            score += 10.0
        elif drawdown >= -30:
            score += 4.0
        elif drawdown <= -60:
            score -= 12.0

    if freshness == "FRESH":
        score += 10.0
    elif freshness == "AGING":
        score += 3.0
    elif freshness == "STALE":
        score -= 15.0

    score -= quality_penalty(quality, admission)

    return max(0.0, min(100.0, score))


def purchase_state(
    *,
    history_class: str,
    score: float,
    freshness: str,
    quality: str,
    admission: str,
    cagr: float | None,
    return_365d: float | None,
    drawdown: float | None,
) -> str:
    if quality == "EXCLUDE_FROM_MODEL":
        return "NOT_PURCHASE_READY"

    if admission == "STRUCTURAL_ONLY":
        return "NOT_PURCHASE_READY"

    if history_class in {"NO_HISTORY", "SINGLE_DATE", "MINIMAL_HISTORY"}:
        return "INSUFFICIENT_HISTORY"

    if freshness == "STALE":
        return "PRICE_VERIFICATION_REQUIRED"

    if quality == "REVIEW_REQUIRED":
        return "MANUAL_REVIEW_REQUIRED"

    if (
        score >= 70
        and cagr is not None
        and cagr >= 8
        and (return_365d is None or return_365d >= -10)
        and (drawdown is None or drawdown >= -40)
    ):
        return "HISTORICALLY_STRONG"

    if (
        score >= 55
        and cagr is not None
        and cagr > 0
        and (drawdown is None or drawdown >= -50)
    ):
        return "HISTORICALLY_STABLE"

    if cagr is not None and cagr > 0:
        return "POSITIVE_BUT_VOLATILE"

    return "NOT_PURCHASE_READY"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    history_rows = read_csv(HISTORY)
    coverage_rows = read_csv(COVERAGE)
    interface_rows = read_csv(INTERFACE)

    coverage_lookup = {
        clean(row.get("canonical_product_id")): row
        for row in coverage_rows
    }

    interface_lookup = {
        clean(row.get("canonical_product_id")): row
        for row in interface_rows
    }

    invalid_rows: list[dict[str, str]] = []
    grouped_prices: dict[
        tuple[str, date],
        list[float],
    ] = defaultdict(list)

    product_metadata: dict[str, dict[str, str]] = {}

    for row in history_rows:
        source_name = clean(row.get("source_name")).upper()
        source_type = clean(row.get("source_type")).upper()
        observation_type = clean(row.get("observation_type")).upper()

        if (
            "ASKING" in source_name
            or "ASKING" in source_type
            or "ASKING" in observation_type
            or "CURRENT_LISTING" in source_name
            or "CURRENT_LISTING" in source_type
        ):
            continue

        product_id = clean(row.get("canonical_product_id"))
        observed_date = parse_date(row.get("observation_date"))
        price = (
            number(row.get("market_price"))
            or number(row.get("consolidated_market_price"))
            or number(row.get("daily_market_price"))
            or number(row.get("observed_price"))
            or number(row.get("price_usd"))
            or number(row.get("median_price_usd"))
            or number(row.get("low_price"))
        )

        if not product_id or observed_date is None or price is None:
            invalid_rows.append(
                {
                    **row,
                    "audit_reason": "MISSING_ID_DATE_OR_PRICE",
                }
            )
            continue

        if price < MIN_PRICE or price > MAX_PRICE:
            invalid_rows.append(
                {
                    **row,
                    "audit_reason": "PRICE_OUTSIDE_PLAUSIBILITY_RANGE",
                }
            )
            continue

        grouped_prices[(product_id, observed_date)].append(price)

        product_metadata[product_id] = {
            "canonical_product_name": clean(
                row.get("canonical_product_name")
            ),
            "product_class": clean(row.get("product_class")),
        }

    consolidated: dict[str, list[tuple[date, float]]] = defaultdict(list)

    for (product_id, observed_date), prices in grouped_prices.items():
        consolidated[product_id].append(
            (observed_date, statistics.median(prices))
        )

    for product_id in consolidated:
        consolidated[product_id].sort(key=lambda item: item[0])

    output_rows: list[dict[str, Any]] = []

    for product_id, observations in consolidated.items():
        metadata = product_metadata.get(product_id, {})
        interface = interface_lookup.get(product_id, {})
        coverage = coverage_lookup.get(product_id, {})

        first_date, first_price = observations[0]
        latest_date, latest_price = observations[-1]

        span_days = (latest_date - first_date).days
        distinct_dates = len(observations)
        total_return = pct_change(first_price, latest_price)
        lifetime_cagr = annualized_return(
            first_price,
            latest_price,
            span_days,
        )

        one_year_anchor = nearest_prior_price(
            observations,
            date(
                latest_date.year - 1,
                latest_date.month,
                min(latest_date.day, 28),
            ),
        )

        three_year_anchor = nearest_prior_price(
            observations,
            date(
                latest_date.year - 3,
                latest_date.month,
                min(latest_date.day, 28),
            ),
        )

        return_365d = (
            pct_change(one_year_anchor[1], latest_price)
            if one_year_anchor
            else None
        )

        return_3y = (
            pct_change(three_year_anchor[1], latest_price)
            if three_year_anchor
            else None
        )

        realized_3y_cagr = (
            annualized_return(
                three_year_anchor[1],
                latest_price,
                (latest_date - three_year_anchor[0]).days,
            )
            if three_year_anchor
            else None
        )

        volatility = annualized_volatility(observations)
        drawdown = maximum_drawdown(observations)

        age_days = (AS_OF_DATE - latest_date).days
        fresh_state = freshness_state(age_days)
        history_class = classify_history(distinct_dates, span_days)

        quality = clean(interface.get("quality_disposition"))
        admission = clean(interface.get("admission_tier"))

        score = calculate_score(
            history_class=history_class,
            total_return=total_return,
            cagr=lifetime_cagr,
            return_365d=return_365d,
            volatility=volatility,
            drawdown=drawdown,
            freshness=fresh_state,
            quality=quality,
            admission=admission,
        )

        state = purchase_state(
            history_class=history_class,
            score=score,
            freshness=fresh_state,
            quality=quality,
            admission=admission,
            cagr=lifetime_cagr,
            return_365d=return_365d,
            drawdown=drawdown,
        )

        output_rows.append(
            {
                "canonical_product_id": product_id,
                "canonical_product_name": metadata.get(
                    "canonical_product_name",
                    clean(interface.get("canonical_product_name")),
                ),
                "product_class": metadata.get(
                    "product_class",
                    clean(interface.get("product_class")),
                ),
                "admission_tier": admission,
                "quality_disposition": quality,
                "history_class": history_class,
                "observation_count": distinct_dates,
                "first_observation_date": first_date.isoformat(),
                "latest_observation_date": latest_date.isoformat(),
                "history_span_days": span_days,
                "latest_price_usd": round_or_blank(latest_price),
                "first_price_usd": round_or_blank(first_price),
                "historical_total_return_pct": round_or_blank(total_return),
                "historical_lifetime_cagr_pct": round_or_blank(lifetime_cagr),
                "historical_return_365d_pct": round_or_blank(return_365d),
                "historical_return_3y_pct": round_or_blank(return_3y),
                "historical_realized_3y_cagr_pct": round_or_blank(
                    realized_3y_cagr
                ),
                "annualized_monthly_volatility_pct": round_or_blank(
                    volatility
                ),
                "maximum_historical_drawdown_pct": round_or_blank(drawdown),
                "price_age_days": age_days,
                "freshness_state": fresh_state,
                "historical_strength_score": f"{score:.2f}",
                "historical_purchase_state": state,
                "direct_history_observation_count": clean(
                    coverage.get("direct_history_observation_count")
                ),
                "history_verification_status": clean(
                    coverage.get("history_verification_status")
                ),
                "governed_forecast_eligible": clean(
                    interface.get("governed_forecast_eligible")
                ),
                "governed_recommendation_eligible": clean(
                    interface.get("governed_recommendation_eligible")
                ),
                "analysis_is_forecast": "false",
                "analysis_basis": (
                    "REALIZED_CONSOLIDATED_HISTORICAL_PRICE_PERFORMANCE"
                ),
            }
        )

    output_rows.sort(
        key=lambda row: (
            -float(row["historical_strength_score"]),
            row["product_class"],
            row["canonical_product_name"],
        )
    )

    candidate_states = {
        "HISTORICALLY_STRONG",
        "HISTORICALLY_STABLE",
    }

    candidates = [
        row
        for row in output_rows
        if row["historical_purchase_state"] in candidate_states
    ]

    manual_review = [
        row
        for row in output_rows
        if row["historical_purchase_state"]
        in {
            "POSITIVE_BUT_VOLATILE",
            "MANUAL_REVIEW_REQUIRED",
            "PRICE_VERIFICATION_REQUIRED",
        }
    ]

    rejected = [
        row
        for row in output_rows
        if row["historical_purchase_state"]
        in {
            "NOT_PURCHASE_READY",
            "INSUFFICIENT_HISTORY",
        }
    ]

    write_csv(
        OUTPUT / "04_historical_product_metrics.csv",
        output_rows,
    )
    write_csv(
        OUTPUT / "05_historical_purchase_candidates.csv",
        candidates,
    )
    write_csv(
        OUTPUT / "06_historical_manual_review.csv",
        manual_review,
    )
    write_csv(
        OUTPUT / "07_historical_not_purchase_ready.csv",
        rejected,
    )
    write_csv(
        OUTPUT / "08_invalid_history_rows.csv",
        invalid_rows,
    )

    state_counts = Counter(
        row["historical_purchase_state"]
        for row in output_rows
    )

    class_counts = Counter(
        row["product_class"]
        for row in output_rows
    )

    candidate_class_counts = Counter(
        row["product_class"]
        for row in candidates
    )

    history_class_counts = Counter(
        row["history_class"]
        for row in output_rows
    )

    summary = {
        "generated_at": datetime.now().isoformat(),
        "as_of_date": AS_OF_DATE.isoformat(),
        "history_source": str(HISTORY.relative_to(ROOT)),
        "history_input_rows": len(history_rows),
        "valid_product_date_rows": len(grouped_prices),
        "products_analyzed": len(output_rows),
        "invalid_history_rows": len(invalid_rows),
        "candidate_products": len(candidates),
        "manual_review_products": len(manual_review),
        "not_purchase_ready_products": len(rejected),
        "state_counts": dict(sorted(state_counts.items())),
        "product_class_counts": dict(sorted(class_counts.items())),
        "candidate_class_counts": dict(
            sorted(candidate_class_counts.items())
        ),
        "history_class_counts": dict(
            sorted(history_class_counts.items())
        ),
        "important_limitations": [
            "This is historical performance analysis, not a forecast.",
            "Historical returns do not establish future returns.",
            "Latest historical prices may not equal executable purchase prices.",
            "Candidate products require exact current-price and identity verification.",
            "Fees, shipping, taxes, spreads, and resale liquidity are not yet applied.",
        ],
    }

    (
        OUTPUT / "09_historical_purchase_summary.json"
    ).write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




