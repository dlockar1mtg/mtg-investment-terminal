from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

OUTPUT = (
    ROOT
    / "artifacts"
    / "weekend_readiness"
    / "20260730-163101"
    / "historical_purchase_screen"
)

METRICS = OUTPUT / "04_historical_product_metrics.csv"
SOURCE_PROFILE = OUTPUT / "23_product_source_dependence.csv"
CANONICAL_HISTORY = OUTPUT / "16_canonical_governed_daily_history.csv"

RANKED_OUTPUT = OUTPUT / "26_calibrated_historical_ranking.csv"
SHORTLIST_OUTPUT = OUTPUT / "27_weekend_verification_shortlist.csv"
REVIEW_OUTPUT = OUTPUT / "28_calibrated_manual_review.csv"
SUMMARY_OUTPUT = OUTPUT / "29_calibrated_ranking_summary.json"


ELIGIBLE_STATES = {
    "HISTORICALLY_STRONG",
    "HISTORICALLY_STABLE",
}

ELIGIBLE_HISTORY = {
    "MEDIUM_HISTORY",
    "LONG_HISTORY",
}

TARGET_SHORTLIST_BY_CLASS = {
    "COLLECTOR_BOOSTER_BOX": 15,
    "PRE_COLLECTOR_BOOSTER_BOX": 15,
    "SECRET_LAIR": 20,
}

MIN_TRUSTED_DATES = 8
MAX_PRICE_AGE_DAYS = 120

# Maximum-entry-price discounts relative to trusted historical value.
ENTRY_DISCOUNT_BY_TIER = {
    "A": 0.90,
    "B": 0.85,
    "C": 0.80,
}


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
    return int(parsed) if parsed is not None else 0


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if fields is None:
        fields = list(rows[0].keys()) if rows else []

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def percentile_rank(
    value: float | None,
    population: list[float],
    *,
    higher_is_better: bool = True,
) -> float:
    if value is None or not population:
        return 0.0

    ordered = sorted(population)

    if len(ordered) == 1:
        percentile = 100.0
    else:
        below = sum(item < value for item in ordered)
        equal = sum(item == value for item in ordered)
        percentile = (
            (below + 0.5 * equal)
            / len(ordered)
            * 100.0
        )

    if not higher_is_better:
        percentile = 100.0 - percentile

    return max(0.0, min(100.0, percentile))


def latest_ebay_evidence(
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    ebay_rows = [
        row
        for row in rows
        if "EBAY" in clean(row.get("source_names")).upper()
    ]

    if not ebay_rows:
        return {
            "latest_ebay_date": "",
            "ebay_reference_price_usd": "",
            "ebay_minimum_price_usd": "",
            "ebay_maximum_price_usd": "",
            "ebay_raw_observation_count": 0,
        }

    latest_date = max(
        clean(row.get("observation_date"))
        for row in ebay_rows
    )

    latest_rows = [
        row
        for row in ebay_rows
        if clean(row.get("observation_date")) == latest_date
    ]

    reference_prices = [
        value
        for row in latest_rows
        if (
            value := number(
                row.get("consolidated_market_price")
            )
        ) is not None
    ]

    minimum_prices = [
        value
        for row in latest_rows
        if (
            value := number(
                row.get("minimum_observed_price")
            )
        ) is not None
    ]

    maximum_prices = [
        value
        for row in latest_rows
        if (
            value := number(
                row.get("maximum_observed_price")
            )
        ) is not None
    ]

    return {
        "latest_ebay_date": latest_date,
        "ebay_reference_price_usd": (
            f"{statistics.median(reference_prices):.2f}"
            if reference_prices
            else ""
        ),
        "ebay_minimum_price_usd": (
            f"{min(minimum_prices):.2f}"
            if minimum_prices
            else ""
        ),
        "ebay_maximum_price_usd": (
            f"{max(maximum_prices):.2f}"
            if maximum_prices
            else ""
        ),
        "ebay_raw_observation_count": sum(
            integer(row.get("raw_observation_count"))
            for row in latest_rows
        ),
    }


def ranking_tier(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    return "C"


def price_relation(
    ebay_price: float | None,
    trusted_price: float | None,
) -> tuple[str, str]:
    if (
        ebay_price is None
        or trusted_price is None
        or trusted_price <= 0
    ):
        return "NO_CURRENT_LISTING_COMPARISON", ""

    premium = (
        (ebay_price / trusted_price) - 1.0
    ) * 100.0

    if premium <= -10:
        state = "LISTING_BELOW_TRUSTED_VALUE"
    elif premium <= 10:
        state = "LISTING_NEAR_TRUSTED_VALUE"
    elif premium <= 25:
        state = "LISTING_MODERATELY_ABOVE_VALUE"
    else:
        state = "LISTING_MATERIALLY_ABOVE_VALUE"

    return state, f"{premium:.2f}"


def main() -> int:
    metric_rows = read_csv(METRICS)
    source_rows = read_csv(SOURCE_PROFILE)
    history_rows = read_csv(CANONICAL_HISTORY)

    source_lookup = {
        clean(row.get("canonical_product_id")): row
        for row in source_rows
    }

    history_by_product: dict[
        str,
        list[dict[str, str]],
    ] = defaultdict(list)

    for row in history_rows:
        history_by_product[
            clean(row.get("canonical_product_id"))
        ].append(row)

    eligible: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []

    for row in metric_rows:
        product_id = clean(
            row.get("canonical_product_id")
        )
        source = source_lookup.get(product_id, {})

        trusted_dates = integer(
            source.get("trusted_dates")
        )

        rejection_reasons: list[str] = []

        if (
            clean(row.get("historical_purchase_state"))
            not in ELIGIBLE_STATES
        ):
            rejection_reasons.append(
                "NOT_IN_HISTORICAL_CANDIDATE_STATE"
            )

        if (
            clean(row.get("history_class"))
            not in ELIGIBLE_HISTORY
        ):
            rejection_reasons.append(
                "HISTORY_NOT_MEDIUM_OR_LONG"
            )

        if trusted_dates < MIN_TRUSTED_DATES:
            rejection_reasons.append(
                "INSUFFICIENT_TRUSTED_DATES"
            )

        if (
            clean(row.get("quality_disposition"))
            == "EXCLUDE_FROM_MODEL"
        ):
            rejection_reasons.append(
                "QUALITY_EXCLUDED"
            )

        if (
            clean(row.get("admission_tier"))
            == "STRUCTURAL_ONLY"
        ):
            rejection_reasons.append(
                "STRUCTURAL_ONLY"
            )

        if (
            integer(row.get("price_age_days"))
            > MAX_PRICE_AGE_DAYS
        ):
            rejection_reasons.append(
                "TRUSTED_PRICE_TOO_OLD"
            )

        prepared = {
            **row,
            "trusted_dates": trusted_dates,
            "source_state": clean(
                source.get("source_state")
            ),
            "ranking_exclusion_reasons": "|".join(
                rejection_reasons
            ),
        }

        if rejection_reasons:
            review.append(prepared)
        else:
            eligible.append(prepared)

    by_class: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in eligible:
        by_class[
            clean(row.get("product_class"))
        ].append(row)

    ranked: list[dict[str, Any]] = []

    for product_class, class_rows in by_class.items():
        cagr_population = [
            value
            for row in class_rows
            if (
                value := number(
                    row.get(
                        "historical_lifetime_cagr_pct"
                    )
                )
            ) is not None
        ]

        return_population = [
            value
            for row in class_rows
            if (
                value := number(
                    row.get(
                        "historical_return_365d_pct"
                    )
                )
            ) is not None
        ]

        volatility_population = [
            value
            for row in class_rows
            if (
                value := number(
                    row.get(
                        "annualized_monthly_volatility_pct"
                    )
                )
            ) is not None
        ]

        drawdown_population = [
            value
            for row in class_rows
            if (
                value := number(
                    row.get(
                        "maximum_historical_drawdown_pct"
                    )
                )
            ) is not None
        ]

        depth_population = [
            float(integer(row.get("trusted_dates")))
            for row in class_rows
        ]

        for row in class_rows:
            cagr = number(
                row.get(
                    "historical_lifetime_cagr_pct"
                )
            )
            recent_return = number(
                row.get(
                    "historical_return_365d_pct"
                )
            )
            volatility = number(
                row.get(
                    "annualized_monthly_volatility_pct"
                )
            )
            drawdown = number(
                row.get(
                    "maximum_historical_drawdown_pct"
                )
            )
            trusted_dates = float(
                integer(row.get("trusted_dates"))
            )

            cagr_percentile = percentile_rank(
                cagr,
                cagr_population,
            )

            recent_percentile = percentile_rank(
                recent_return,
                return_population,
            )

            volatility_percentile = percentile_rank(
                volatility,
                volatility_population,
                higher_is_better=False,
            )

            # Less-negative drawdown is better.
            drawdown_percentile = percentile_rank(
                drawdown,
                drawdown_population,
            )

            depth_percentile = percentile_rank(
                trusted_dates,
                depth_population,
            )

            calibrated_score = (
                0.30 * cagr_percentile
                + 0.20 * recent_percentile
                + 0.20 * volatility_percentile
                + 0.20 * drawdown_percentile
                + 0.10 * depth_percentile
            )

            tier = ranking_tier(calibrated_score)

            trusted_price = number(
                row.get("latest_price_usd")
            )

            maximum_entry_price = (
                trusted_price
                * ENTRY_DISCOUNT_BY_TIER[tier]
                if trusted_price is not None
                else None
            )

            ebay = latest_ebay_evidence(
                history_by_product.get(
                    clean(
                        row.get(
                            "canonical_product_id"
                        )
                    ),
                    [],
                )
            )

            ebay_price = number(
                ebay.get(
                    "ebay_reference_price_usd"
                )
            )

            relation_state, premium = price_relation(
                ebay_price,
                trusted_price,
            )

            entry_state = (
                "CURRENT_LISTING_WITHIN_ENTRY_LIMIT"
                if (
                    ebay_price is not None
                    and maximum_entry_price is not None
                    and ebay_price <= maximum_entry_price
                )
                else (
                    "CURRENT_LISTING_ABOVE_ENTRY_LIMIT"
                    if ebay_price is not None
                    else "CURRENT_PRICE_VERIFICATION_REQUIRED"
                )
            )

            ranked.append(
                {
                    **row,
                    "cagr_class_percentile": (
                        f"{cagr_percentile:.2f}"
                    ),
                    "recent_return_class_percentile": (
                        f"{recent_percentile:.2f}"
                    ),
                    "volatility_class_percentile": (
                        f"{volatility_percentile:.2f}"
                    ),
                    "drawdown_class_percentile": (
                        f"{drawdown_percentile:.2f}"
                    ),
                    "history_depth_class_percentile": (
                        f"{depth_percentile:.2f}"
                    ),
                    "calibrated_score": (
                        f"{calibrated_score:.2f}"
                    ),
                    "calibrated_tier": tier,
                    "preliminary_maximum_entry_price_usd": (
                        f"{maximum_entry_price:.2f}"
                        if maximum_entry_price is not None
                        else ""
                    ),
                    **ebay,
                    "ebay_vs_trusted_value_pct": premium,
                    "listing_value_relation": relation_state,
                    "preliminary_entry_state": entry_state,
                    "ranking_basis": (
                        "WITHIN_CLASS_HISTORICAL_PERCENTILE_MODEL"
                    ),
                    "ranking_is_forecast": "false",
                }
            )

    ranked.sort(
        key=lambda row: (
            clean(row.get("product_class")),
            -float(row["calibrated_score"]),
            clean(row.get("canonical_product_name")),
        )
    )

    class_rank_counter: dict[str, int] = defaultdict(int)

    for row in ranked:
        product_class = clean(
            row.get("product_class")
        )
        class_rank_counter[product_class] += 1
        row["class_rank"] = class_rank_counter[
            product_class
        ]

    shortlist: list[dict[str, Any]] = []

    for row in ranked:
        product_class = clean(
            row.get("product_class")
        )

        limit = TARGET_SHORTLIST_BY_CLASS.get(
            product_class,
            0,
        )

        if int(row["class_rank"]) <= limit:
            shortlist.append(row)

    write_csv(RANKED_OUTPUT, ranked)
    write_csv(SHORTLIST_OUTPUT, shortlist)
    write_csv(REVIEW_OUTPUT, review)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "metric_products": len(metric_rows),
        "eligible_for_calibrated_ranking": len(eligible),
        "ranked_products": len(ranked),
        "shortlist_products": len(shortlist),
        "manual_review_or_excluded": len(review),
        "shortlist_by_class": {
            product_class: sum(
                1
                for row in shortlist
                if clean(row.get("product_class"))
                == product_class
            )
            for product_class in sorted(
                TARGET_SHORTLIST_BY_CLASS
            )
        },
        "tier_counts": {
            tier: sum(
                1
                for row in ranked
                if row["calibrated_tier"] == tier
            )
            for tier in ("A", "B", "C")
        },
        "entry_state_counts": {
            state: sum(
                1
                for row in shortlist
                if row["preliminary_entry_state"]
                == state
            )
            for state in sorted(
                {
                    row["preliminary_entry_state"]
                    for row in shortlist
                }
            )
        },
        "important_limitations": [
            "The calibrated score is historical and relative within product class.",
            "The maximum entry price is preliminary, not a live purchase instruction.",
            "eBay values are listing evidence and may not represent completed transactions.",
            "Every shortlisted product requires exact identity, condition, shipping, tax, and seller verification.",
            "No result is a certified forward forecast.",
        ],
    }

    SUMMARY_OUTPUT.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
