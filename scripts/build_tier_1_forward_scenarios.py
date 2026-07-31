from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
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

INPUT = (
    OUTPUT
    / "35_tier_1_full_historical_analysis.csv"
)

FORECAST_OUTPUT = (
    OUTPUT
    / "40_tier_1_forward_scenario_projections.csv"
)

REVIEW_OUTPUT = (
    OUTPUT
    / "41_tier_1_projection_review_required.csv"
)

TOP_OUTPUT = (
    OUTPUT
    / "42_tier_1_projection_priority_view.csv"
)

SUMMARY_OUTPUT = (
    OUTPUT
    / "43_tier_1_forward_scenario_summary.json"
)


CLASS_ASSUMPTIONS = {
    "COLLECTOR_BOOSTER_BOX": {
        "conservative_anchor": 1.0,
        "base_anchor": 6.0,
        "high_anchor": 12.0,
        "base_floor": -5.0,
        "base_cap": 15.0,
        "high_cap": 24.0,
    },
    "PRE_COLLECTOR_BOOSTER_BOX": {
        "conservative_anchor": 1.0,
        "base_anchor": 5.0,
        "high_anchor": 10.0,
        "base_floor": -5.0,
        "base_cap": 14.0,
        "high_cap": 21.0,
    },
    "SECRET_LAIR": {
        "conservative_anchor": 0.0,
        "base_anchor": 5.0,
        "high_anchor": 11.0,
        "base_floor": -7.0,
        "base_cap": 16.0,
        "high_cap": 25.0,
    },
}

MIN_REQUIRED_TRUSTED_DATES = 8
MAX_ALLOWED_PRICE_AGE_DAYS = 120


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    text = (
        clean(value)
        .replace("$", "")
        .replace(",", "")
        .replace("%", "")
    )

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


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(maximum, value),
    )


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
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if fields is None:
        fields = (
            list(rows[0].keys())
            if rows
            else []
        )

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
    value: float,
    population: list[float],
) -> float:
    if not population:
        return 50.0

    below = sum(
        item < value
        for item in population
    )

    equal = sum(
        item == value
        for item in population
    )

    return (
        (
            below
            + 0.5 * equal
        )
        / len(population)
        * 100.0
    )


def projection(
    current_value: float,
    annual_rate_pct: float,
    years: int,
) -> float:
    rate = annual_rate_pct / 100.0

    return current_value * (
        (1.0 + rate) ** years
    )


def confidence_label(score: float) -> str:
    if score >= 80:
        return "HIGH"
    if score >= 65:
        return "MODERATE_HIGH"
    if score >= 50:
        return "MODERATE"
    return "LOW"


def projection_state(
    confidence_score: float,
    price_age_days: int,
    uncertainty_penalty: float,
) -> str:
    if price_age_days > MAX_ALLOWED_PRICE_AGE_DAYS:
        return "CURRENT_VALUE_REFRESH_REQUIRED"

    if confidence_score < 50:
        return "SCENARIO_REVIEW_REQUIRED"

    if uncertainty_penalty >= 30:
        return "ELEVATED_UNCERTAINTY"

    return "SCENARIO_MODEL_READY"


def calculate_forward_rates(
    row: dict[str, str],
    class_population: dict[str, list[float]],
) -> dict[str, float]:
    product_class = clean(
        row.get("product_class")
    )

    assumptions = CLASS_ASSUMPTIONS[
        product_class
    ]

    historical_cagr = (
        number(
            row.get(
                "historical_lifetime_cagr_pct"
            )
        )
        or 0.0
    )

    recent_return = (
        number(
            row.get(
                "historical_return_365d_pct"
            )
        )
        or 0.0
    )

    volatility = abs(
        number(
            row.get(
                "annualized_monthly_volatility_pct"
            )
        )
        or 0.0
    )

    drawdown = abs(
        number(
            row.get(
                "maximum_historical_drawdown_pct"
            )
        )
        or 0.0
    )

    coverage_score = (
        number(
            row.get(
                "history_coverage_score"
            )
        )
        or 0.0
    )

    risk_score = (
        number(
            row.get(
                "historical_risk_score"
            )
        )
        or 0.0
    )

    analytical_percentile = (
        number(
            row.get(
                "within_class_analytical_percentile"
            )
        )
        or 50.0
    )

    uncertainty = (
        number(
            row.get(
                "uncertainty_penalty"
            )
        )
        or 0.0
    )

    class_cagr_values = class_population[
        product_class
    ]

    cagr_percentile = percentile_rank(
        historical_cagr,
        class_cagr_values,
    )

    # Convert extreme historical results into diminishing forward influence.
    capped_historical = max(
        -30.0,
        min(historical_cagr, 100.0),
    )

    capped_recent = max(
        -30.0,
        min(recent_return, 100.0),
    )

    historical_signal = (
        math.copysign(
            math.sqrt(abs(capped_historical)),
            capped_historical,
        )
        if capped_historical != 0
        else 0.0
    )

    recent_signal = (
        math.copysign(
            math.sqrt(abs(capped_recent)),
            capped_recent,
        )
        if capped_recent != 0
        else 0.0
    )

    moderated_historical = (
        0.40 * historical_signal
        + 0.20 * recent_signal
    )

    quality_adjustment = (
        0.018 * (
            coverage_score - 50.0
        )
        + 0.015 * (
            risk_score - 50.0
        )
        + 0.012 * (
            analytical_percentile - 50.0
        )
        + 0.008 * (
            cagr_percentile - 50.0
        )
    )

    risk_penalty = (
        min(volatility, 120.0) * 0.035
        + min(drawdown, 100.0) * 0.045
        + uncertainty * 0.060
    )

    base_rate = (
        assumptions["base_anchor"]
        + moderated_historical
        + quality_adjustment
        - risk_penalty
    )

    base_rate = clamp(
        base_rate,
        assumptions["base_floor"],
        assumptions["base_cap"],
    )

    scenario_width = (
        3.0
        + min(volatility, 100.0) * 0.045
        + min(drawdown, 80.0) * 0.040
        + uncertainty * 0.040
    )

    conservative_rate = min(
        assumptions[
            "conservative_anchor"
        ],
        base_rate - scenario_width,
    )

    conservative_rate = clamp(
        conservative_rate,
        -12.0,
        assumptions["base_cap"],
    )

    high_rate = max(
        assumptions["high_anchor"],
        base_rate + scenario_width,
    )

    high_rate = clamp(
        high_rate,
        base_rate,
        assumptions["high_cap"],
    )

    return {
        "historical_cagr_percentile": (
            cagr_percentile
        ),
        "forward_cagr_conservative_pct": (
            conservative_rate
        ),
        "forward_cagr_base_pct": base_rate,
        "forward_cagr_high_pct": high_rate,
        "scenario_width_pct": (
            high_rate - conservative_rate
        ),
    }


def main() -> int:
    rows = read_csv(INPUT)

    if len(rows) != 783:
        raise RuntimeError(
            "Expected 783 Tier 1 products, "
            f"found {len(rows)}."
        )

    class_population: dict[
        str,
        list[float],
    ] = defaultdict(list)

    for row in rows:
        product_class = clean(
            row.get("product_class")
        )

        historical_cagr = number(
            row.get(
                "historical_lifetime_cagr_pct"
            )
        )

        if historical_cagr is not None:
            class_population[
                product_class
            ].append(historical_cagr)

    forecast_rows: list[
        dict[str, Any]
    ] = []

    review_rows: list[
        dict[str, Any]
    ] = []

    for row in rows:
        product_id = clean(
            row.get("canonical_product_id")
        )

        current_value = number(
            row.get(
                "current_market_value_usd"
            )
        )

        historical_cagr = number(
            row.get(
                "historical_lifetime_cagr_pct"
            )
        )

        recent_return = number(
            row.get(
                "historical_return_365d_pct"
            )
        )

        trusted_dates = integer(
            row.get("trusted_dates")
        )

        price_age_days = integer(
            row.get("price_age_days")
        )

        coverage_score = (
            number(
                row.get(
                    "history_coverage_score"
                )
            )
            or 0.0
        )

        quality_score = (
            number(
                row.get("quality_score")
            )
            or 0.0
        )

        valuation_score = (
            number(
                row.get(
                    "valuation_evidence_score"
                )
            )
            or 0.0
        )

        uncertainty = (
            number(
                row.get(
                    "uncertainty_penalty"
                )
            )
            or 0.0
        )

        review_reasons: list[str] = []

        if current_value is None:
            review_reasons.append(
                "MISSING_CURRENT_MARKET_VALUE"
            )

        if historical_cagr is None:
            review_reasons.append(
                "MISSING_HISTORICAL_CAGR"
            )

        if recent_return is None:
            review_reasons.append(
                "MISSING_RECENT_RETURN"
            )

        if trusted_dates < MIN_REQUIRED_TRUSTED_DATES:
            review_reasons.append(
                "INSUFFICIENT_TRUSTED_DATES"
            )

        if clean(
            row.get("evidence_tier")
        ) != "TIER_1":
            review_reasons.append(
                "NOT_TIER_1"
            )

        confidence_score = (
            0.30 * coverage_score
            + 0.25 * quality_score
            + 0.20 * valuation_score
            + 0.15 * min(
                100.0,
                trusted_dates / 30.0 * 100.0,
            )
            + 0.10 * max(
                0.0,
                100.0 - uncertainty,
            )
        )

        if price_age_days > 120:
            confidence_score -= 15.0
        elif price_age_days > 45:
            confidence_score -= 5.0

        confidence_score = clamp(
            confidence_score,
            0.0,
            100.0,
        )

        prepared_base = {
            **row,
            "projection_model_version": (
                "TIER_1_FORWARD_SCENARIO_V2_RECALIBRATED"
            ),
            "projection_as_of_date": (
                "2026-07-30"
            ),
            "forecast_confidence_score": (
                f"{confidence_score:.2f}"
            ),
            "forecast_confidence_label": (
                confidence_label(
                    confidence_score
                )
            ),
            "projection_state": (
                projection_state(
                    confidence_score,
                    price_age_days,
                    uncertainty,
                )
            ),
            "projection_review_reasons": (
                "|".join(review_reasons)
            ),
            "projection_is_certified_forecast": (
                "false"
            ),
            "projection_is_scenario_analysis": (
                "true"
            ),
            "projection_method": (
                "MODERATED_HISTORICAL_CLASS_ANCHORED_SCENARIO_MODEL"
            ),
        }

        if review_reasons:
            review_rows.append(
                prepared_base
            )
            continue

        assert current_value is not None

        rates = calculate_forward_rates(
            row,
            class_population,
        )

        conservative_rate = rates[
            "forward_cagr_conservative_pct"
        ]

        base_rate = rates[
            "forward_cagr_base_pct"
        ]

        high_rate = rates[
            "forward_cagr_high_pct"
        ]

        projections: dict[str, str] = {}

        for years in (1, 3, 5):
            projections[
                f"projected_value_{years}y_conservative_usd"
            ] = (
                f"{projection(
                    current_value,
                    conservative_rate,
                    years,
                ):.2f}"
            )

            projections[
                f"projected_value_{years}y_base_usd"
            ] = (
                f"{projection(
                    current_value,
                    base_rate,
                    years,
                ):.2f}"
            )

            projections[
                f"projected_value_{years}y_high_usd"
            ] = (
                f"{projection(
                    current_value,
                    high_rate,
                    years,
                ):.2f}"
            )

        forecast_rows.append(
            {
                **prepared_base,
                "historical_cagr_percentile": (
                    f"{rates[
                        'historical_cagr_percentile'
                    ]:.2f}"
                ),
                "forward_cagr_conservative_pct": (
                    f"{conservative_rate:.2f}"
                ),
                "forward_cagr_base_pct": (
                    f"{base_rate:.2f}"
                ),
                "forward_cagr_high_pct": (
                    f"{high_rate:.2f}"
                ),
                "scenario_width_pct": (
                    f"{rates[
                        'scenario_width_pct'
                    ]:.2f}"
                ),
                **projections,
                "projection_limitations": (
                    "SCENARIO_NOT_GUARANTEE|"
                    "CURRENT_VALUE_REQUIRES_VERIFICATION|"
                    "HISTORICAL_RETURNS_MEAN_REVERTED|"
                    "FEES_TAXES_SHIPPING_AND_LIQUIDITY_NOT_APPLIED"
                ),
            }
        )

    forecast_rows.sort(
        key=lambda row: (
            clean(row.get("product_class")),
            -float(
                row[
                    "within_class_analytical_percentile"
                ]
            ),
            -float(
                row[
                    "forecast_confidence_score"
                ]
            ),
            clean(
                row.get(
                    "canonical_product_name"
                )
            ),
        )
    )

    class_rank_counter: dict[
        str,
        int,
    ] = defaultdict(int)

    for row in forecast_rows:
        product_class = clean(
            row.get("product_class")
        )

        class_rank_counter[
            product_class
        ] += 1

        row[
            "forward_scenario_class_rank"
        ] = class_rank_counter[
            product_class
        ]

    priority_rows = [
        row
        for row in forecast_rows
        if (
            clean(
                row.get(
                    "purchase_readiness_state"
                )
            )
            == "PURCHASE_ANALYSIS_ELIGIBLE"
            and float(
                row[
                    "forecast_confidence_score"
                ]
            ) >= 60.0
        )
    ]

    priority_rows.sort(
        key=lambda row: (
            -float(
                row[
                    "universal_analytical_score"
                ]
            ),
            -float(
                row[
                    "forecast_confidence_score"
                ]
            ),
        )
    )

    write_csv(
        FORECAST_OUTPUT,
        forecast_rows,
    )

    write_csv(
        REVIEW_OUTPUT,
        review_rows,
    )

    write_csv(
        TOP_OUTPUT,
        priority_rows,
    )

    class_counts = Counter(
        row["product_class"]
        for row in forecast_rows
    )

    confidence_counts = Counter(
        row["forecast_confidence_label"]
        for row in forecast_rows
    )

    state_counts = Counter(
        row["projection_state"]
        for row in forecast_rows
    )

    base_rates_by_class: dict[
        str,
        list[float],
    ] = defaultdict(list)

    for row in forecast_rows:
        base_rates_by_class[
            row["product_class"]
        ].append(
            float(
                row[
                    "forward_cagr_base_pct"
                ]
            )
        )

    summary = {
        "generated_at": datetime.now().isoformat(),
        "projection_as_of_date": "2026-07-30",
        "tier_1_input_products": len(rows),
        "scenario_projection_products": len(
            forecast_rows
        ),
        "review_required_products": len(
            review_rows
        ),
        "priority_projection_products": len(
            priority_rows
        ),
        "class_counts": dict(
            sorted(class_counts.items())
        ),
        "confidence_counts": dict(
            sorted(
                confidence_counts.items()
            )
        ),
        "projection_state_counts": dict(
            sorted(state_counts.items())
        ),
        "base_forward_cagr_summary_by_class": {
            product_class: {
                "minimum_pct": round(
                    min(values),
                    2,
                ),
                "median_pct": round(
                    statistics.median(values),
                    2,
                ),
                "maximum_pct": round(
                    max(values),
                    2,
                ),
            }
            for product_class, values
            in sorted(
                base_rates_by_class.items()
            )
        },
        "output_files": {
            "all_tier_1_scenarios": str(
                FORECAST_OUTPUT.relative_to(
                    ROOT
                )
            ),
            "review_required": str(
                REVIEW_OUTPUT.relative_to(
                    ROOT
                )
            ),
            "priority_view": str(
                TOP_OUTPUT.relative_to(
                    ROOT
                )
            ),
        },
        "important_interpretation": [
            "These outputs are scenario projections, not certified forecasts.",
            "Historical CAGR is moderated and not directly extended forward.",
            "Conservative, base, and high rates are class anchored.",
            "Current market values must be verified before purchase decisions.",
            "Projected values exclude fees, taxes, shipping, spreads, and liquidity effects.",
            "Forecast confidence measures input evidence strength, not probability of achieving the projected return.",
        ],
    }

    SUMMARY_OUTPUT.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    if (
        len(forecast_rows)
        + len(review_rows)
        != len(rows)
    ):
        raise RuntimeError(
            "Tier 1 projection population "
            "does not reconcile to input."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())



