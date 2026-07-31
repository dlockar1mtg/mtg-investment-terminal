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

HISTORICAL_ROOT = (
    ROOT
    / "artifacts"
    / "weekend_readiness"
    / "20260730-163101"
    / "historical_purchase_screen"
)

REGISTRY = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "unified_mtg_registry"
    / "unified_mtg_product_registry.csv"
)

METRICS = (
    HISTORICAL_ROOT
    / "04_historical_product_metrics.csv"
)

SOURCE_PROFILE = (
    HISTORICAL_ROOT
    / "23_product_source_dependence.csv"
)

CALIBRATED_RANKING = (
    HISTORICAL_ROOT
    / "26_calibrated_historical_ranking.csv"
)

UNIVERSAL_OUTPUT = (
    HISTORICAL_ROOT
    / "34_universal_tiered_analysis.csv"
)

TIER_1_OUTPUT = (
    HISTORICAL_ROOT
    / "35_tier_1_full_historical_analysis.csv"
)

TIER_2_OUTPUT = (
    HISTORICAL_ROOT
    / "36_tier_2_limited_historical_analysis.csv"
)

TIER_3_OUTPUT = (
    HISTORICAL_ROOT
    / "37_tier_3_current_evidence_analysis.csv"
)

ACTIONABLE_OUTPUT = (
    HISTORICAL_ROOT
    / "38_universal_purchase_action_candidates.csv"
)

SUMMARY_OUTPUT = (
    HISTORICAL_ROOT
    / "39_universal_tiered_analysis_summary.json"
)

AS_OF_DATE = date(2026, 7, 30)


TIER_1_HISTORY_CLASSES = {
    "MEDIUM_HISTORY",
    "LONG_HISTORY",
}

TIER_2_HISTORY_CLASSES = {
    "SHORT_HISTORY",
    "MINIMAL_HISTORY",
}

PURCHASE_CANDIDATE_STATES = {
    "HISTORICALLY_STRONG",
    "HISTORICALLY_STABLE",
}


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


def parse_date(value: Any) -> date | None:
    text = clean(value)[:10]

    if not text:
        return None

    try:
        return datetime.strptime(
            text,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return None


def read_csv(
    path: Path,
    *,
    required: bool = True,
) -> list[dict[str, str]]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []

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


def clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 100.0,
) -> float:
    return max(
        minimum,
        min(maximum, value),
    )


def percentile_rank(
    value: float | None,
    population: list[float],
    *,
    higher_is_better: bool = True,
    missing_score: float = 0.0,
) -> float:
    if value is None or not population:
        return missing_score

    ordered = sorted(population)

    below = sum(
        item < value
        for item in ordered
    )

    equal = sum(
        item == value
        for item in ordered
    )

    percentile = (
        (
            below
            + 0.5 * equal
        )
        / len(ordered)
        * 100.0
    )

    if not higher_is_better:
        percentile = 100.0 - percentile

    return clamp(percentile)


def quality_score(
    quality: str,
    admission: str,
    registry_status: str,
) -> float:
    score = 50.0

    quality_points = {
        "PASS": 35.0,
        "EVALUATED": 25.0,
        "REVIEW_REQUIRED": 5.0,
        "EXCLUDE_FROM_MODEL": -45.0,
    }

    admission_points = {
        "FULL_MODEL": 15.0,
        "PROVISIONAL_MODEL": 0.0,
        "STRUCTURAL_ONLY": -30.0,
    }

    score += quality_points.get(
        quality,
        0.0,
    )

    score += admission_points.get(
        admission,
        0.0,
    )

    if registry_status.upper() in {
        "ACTIVE",
        "ADMITTED",
        "GOVERNED",
    }:
        score += 5.0

    return clamp(score)


def determine_tier(
    *,
    history_class: str,
    trusted_dates: int,
) -> tuple[str, str]:
    if (
        history_class in TIER_1_HISTORY_CLASSES
        and trusted_dates >= 8
    ):
        return (
            "TIER_1",
            "FULL_HISTORICAL_ANALYSIS",
        )

    if (
        history_class in TIER_2_HISTORY_CLASSES
        or 2 <= trusted_dates <= 7
    ):
        return (
            "TIER_2",
            "LIMITED_HISTORICAL_ANALYSIS",
        )

    return (
        "TIER_3",
        "CURRENT_EVIDENCE_AND_COMPARABLES_ONLY",
    )


def history_coverage_score(
    *,
    tier: str,
    trusted_dates: int,
    history_span_days: int,
) -> float:
    date_score = min(
        60.0,
        trusted_dates * 2.0,
    )

    span_score = min(
        40.0,
        history_span_days
        / 730.0
        * 40.0,
    )

    raw_score = date_score + span_score

    if tier == "TIER_1":
        return clamp(raw_score)

    if tier == "TIER_2":
        return clamp(
            min(raw_score, 65.0)
        )

    if trusted_dates == 1:
        return 15.0

    return 0.0


def valuation_evidence_score(
    *,
    current_value: float | None,
    confidence: float | None,
    quality: str,
    trusted_dates: int,
) -> float:
    score = 0.0

    if current_value is not None and current_value > 0:
        score += 45.0

    if confidence is not None:
        if confidence <= 1:
            score += confidence * 35.0
        else:
            score += min(
                35.0,
                confidence,
            )

    if trusted_dates > 0:
        score += min(
            15.0,
            trusted_dates,
        )

    if quality == "PASS":
        score += 5.0
    elif quality == "EXCLUDE_FROM_MODEL":
        score -= 25.0

    return clamp(score)


def uncertainty_penalty(
    *,
    tier: str,
    trusted_dates: int,
    quality: str,
    admission: str,
    price_age_days: int | None,
) -> float:
    penalty = {
        "TIER_1": 5.0,
        "TIER_2": 25.0,
        "TIER_3": 45.0,
    }[tier]

    if trusted_dates == 0:
        penalty += 15.0
    elif trusted_dates == 1:
        penalty += 10.0

    if quality == "REVIEW_REQUIRED":
        penalty += 15.0
    elif quality == "EXCLUDE_FROM_MODEL":
        penalty += 30.0

    if admission == "PROVISIONAL_MODEL":
        penalty += 5.0
    elif admission == "STRUCTURAL_ONLY":
        penalty += 20.0

    if price_age_days is None:
        penalty += 10.0
    elif price_age_days > 120:
        penalty += 15.0
    elif price_age_days > 45:
        penalty += 5.0

    return clamp(
        penalty,
        0.0,
        90.0,
    )


def purchase_readiness(
    *,
    tier: str,
    universal_score: float,
    quality: str,
    admission: str,
    historical_state: str,
    price_age_days: int | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if quality == "EXCLUDE_FROM_MODEL":
        reasons.append("QUALITY_EXCLUDED")

    if admission == "STRUCTURAL_ONLY":
        reasons.append("STRUCTURAL_ONLY")

    if tier == "TIER_3":
        reasons.append(
            "INSUFFICIENT_TRUSTED_HISTORY_FOR_PURCHASE_DECISION"
        )

    if (
        price_age_days is None
        or price_age_days > 120
    ):
        reasons.append(
            "CURRENT_PRICE_VERIFICATION_REQUIRED"
        )

    if reasons:
        if tier == "TIER_3":
            return (
                "RESEARCH_ONLY",
                reasons,
            )

        return (
            "NOT_PURCHASE_READY",
            reasons,
        )

    if (
        tier == "TIER_1"
        and historical_state in PURCHASE_CANDIDATE_STATES
        and universal_score >= 70
    ):
        return (
            "PURCHASE_ANALYSIS_ELIGIBLE",
            [],
        )

    if (
        tier == "TIER_1"
        and universal_score >= 55
    ):
        return (
            "MANUAL_PURCHASE_REVIEW",
            [],
        )

    if tier == "TIER_2":
        return (
            "PROVISIONAL_RESEARCH_CANDIDATE",
            [
                "LIMITED_HISTORY_REQUIRES_ADDITIONAL_EVIDENCE"
            ],
        )

    return (
        "NOT_PURCHASE_READY",
        [
            "UNIVERSAL_SCORE_BELOW_ACTION_THRESHOLD"
        ],
    )


def main() -> int:
    registry_rows = read_csv(REGISTRY)
    metric_rows = read_csv(METRICS)
    source_rows = read_csv(SOURCE_PROFILE)
    calibrated_rows = read_csv(
        CALIBRATED_RANKING,
        required=False,
    )

    metric_lookup = {
        clean(row.get("canonical_product_id")): row
        for row in metric_rows
    }

    source_lookup = {
        clean(row.get("canonical_product_id")): row
        for row in source_rows
    }

    calibrated_lookup = {
        clean(row.get("canonical_product_id")): row
        for row in calibrated_rows
    }

    class_metrics: dict[
        str,
        dict[str, list[float]],
    ] = defaultdict(
        lambda: defaultdict(list)
    )

    for row in metric_rows:
        product_class = clean(
            row.get("product_class")
        )

        metric_fields = {
            "cagr": "historical_lifetime_cagr_pct",
            "recent_return": "historical_return_365d_pct",
            "volatility": "annualized_monthly_volatility_pct",
            "drawdown": "maximum_historical_drawdown_pct",
        }

        for key, field in metric_fields.items():
            value = number(row.get(field))

            if value is not None:
                class_metrics[
                    product_class
                ][key].append(value)

    class_score_populations: dict[
        str,
        list[float],
    ] = defaultdict(list)

    preliminary_rows: list[dict[str, Any]] = []

    for registry in registry_rows:
        product_id = clean(
            registry.get("universal_mtg_product_id")
        )

        metric = metric_lookup.get(
            product_id,
            {},
        )

        source = source_lookup.get(
            product_id,
            {},
        )

        calibrated = calibrated_lookup.get(
            product_id,
            {},
        )

        product_class = clean(
            registry.get("product_class")
        )

        quality = clean(
            registry.get("quality_disposition")
        )

        admission = clean(
            registry.get("admission_tier")
        )

        registry_status = clean(
            registry.get("registry_status")
        )

        trusted_dates = integer(
            source.get("trusted_dates")
        )

        history_class = clean(
            metric.get("history_class")
        )

        history_span_days = integer(
            metric.get("history_span_days")
        )

        tier, analysis_status = determine_tier(
            history_class=history_class,
            trusted_dates=trusted_dates,
        )

        coverage_score = history_coverage_score(
            tier=tier,
            trusted_dates=trusted_dates,
            history_span_days=history_span_days,
        )

        cagr = number(
            metric.get(
                "historical_lifetime_cagr_pct"
            )
        )

        recent_return = number(
            metric.get(
                "historical_return_365d_pct"
            )
        )

        volatility = number(
            metric.get(
                "annualized_monthly_volatility_pct"
            )
        )

        drawdown = number(
            metric.get(
                "maximum_historical_drawdown_pct"
            )
        )

        populations = class_metrics[
            product_class
        ]

        cagr_score = percentile_rank(
            cagr,
            populations["cagr"],
            missing_score=0.0,
        )

        recent_score = percentile_rank(
            recent_return,
            populations["recent_return"],
            missing_score=0.0,
        )

        volatility_score = percentile_rank(
            volatility,
            populations["volatility"],
            higher_is_better=False,
            missing_score=0.0,
        )

        drawdown_score = percentile_rank(
            drawdown,
            populations["drawdown"],
            higher_is_better=True,
            missing_score=0.0,
        )

        historical_performance = (
            0.65 * cagr_score
            + 0.35 * recent_score
        )

        historical_risk = (
            0.50 * volatility_score
            + 0.50 * drawdown_score
        )

        governed_quality_score = quality_score(
            quality,
            admission,
            registry_status,
        )

        current_value = number(
            registry.get(
                "current_market_value_usd"
            )
        )

        confidence = number(
            registry.get("confidence")
        )

        valuation_score = valuation_evidence_score(
            current_value=current_value,
            confidence=confidence,
            quality=quality,
            trusted_dates=trusted_dates,
        )

        latest_date = parse_date(
            metric.get(
                "latest_observation_date"
            )
        )

        price_age_days = (
            (AS_OF_DATE - latest_date).days
            if latest_date is not None
            else None
        )

        penalty = uncertainty_penalty(
            tier=tier,
            trusted_dates=trusted_dates,
            quality=quality,
            admission=admission,
            price_age_days=price_age_days,
        )

        calibrated_score = number(
            calibrated.get("calibrated_score")
        )

        preliminary_rows.append(
            {
                "canonical_product_id": product_id,
                "canonical_product_name": clean(
                    registry.get(
                        "canonical_product_name"
                    )
                ),
                "product_class": product_class,
                "product_group": clean(
                    registry.get("product_group")
                ),
                "finish_group": clean(
                    registry.get("finish_group")
                ),
                "release_date": clean(
                    registry.get("release_date")
                ),
                "registry_status": registry_status,
                "admission_tier": admission,
                "quality_disposition": quality,
                "quality_flags": clean(
                    registry.get("quality_flags")
                ),
                "evidence_tier": tier,
                "universal_analysis_status": analysis_status,
                "history_class": history_class or "NO_TRUSTED_HISTORY",
                "trusted_dates": trusted_dates,
                "total_history_dates": integer(
                    source.get("total_dates")
                ),
                "ebay_dates": integer(
                    source.get("ebay_dates")
                ),
                "source_state": clean(
                    source.get("source_state")
                ) or "NO_HISTORY_SOURCE",
                "history_span_days": history_span_days,
                "latest_observation_date": (
                    latest_date.isoformat()
                    if latest_date is not None
                    else ""
                ),
                "price_age_days": (
                    price_age_days
                    if price_age_days is not None
                    else ""
                ),
                "current_market_value_usd": (
                    f"{current_value:.2f}"
                    if current_value is not None
                    else ""
                ),
                "historical_lifetime_cagr_pct": (
                    f"{cagr:.2f}"
                    if cagr is not None
                    else ""
                ),
                "historical_return_365d_pct": (
                    f"{recent_return:.2f}"
                    if recent_return is not None
                    else ""
                ),
                "annualized_monthly_volatility_pct": (
                    f"{volatility:.2f}"
                    if volatility is not None
                    else ""
                ),
                "maximum_historical_drawdown_pct": (
                    f"{drawdown:.2f}"
                    if drawdown is not None
                    else ""
                ),
                "historical_purchase_state": clean(
                    metric.get(
                        "historical_purchase_state"
                    )
                ) or "NOT_HISTORICALLY_CLASSIFIED",
                "history_coverage_score": (
                    f"{coverage_score:.2f}"
                ),
                "historical_performance_score": (
                    f"{historical_performance:.2f}"
                ),
                "historical_risk_score": (
                    f"{historical_risk:.2f}"
                ),
                "quality_score": (
                    f"{governed_quality_score:.2f}"
                ),
                "valuation_evidence_score": (
                    f"{valuation_score:.2f}"
                ),
                "existing_calibrated_score": (
                    f"{calibrated_score:.2f}"
                    if calibrated_score is not None
                    else ""
                ),
                "uncertainty_penalty": (
                    f"{penalty:.2f}"
                ),
            }
        )

    for product_class in {
        row["product_class"]
        for row in preliminary_rows
    }:
        class_rows = [
            row
            for row in preliminary_rows
            if row["product_class"] == product_class
        ]

        tier_1_performance = [
            number(
                row["historical_performance_score"]
            )
            for row in class_rows
            if (
                row["evidence_tier"] == "TIER_1"
                and number(
                    row[
                        "historical_performance_score"
                    ]
                ) is not None
            )
        ]

        tier_1_risk = [
            number(
                row["historical_risk_score"]
            )
            for row in class_rows
            if (
                row["evidence_tier"] == "TIER_1"
                and number(
                    row["historical_risk_score"]
                ) is not None
            )
        ]

        comparable_performance = (
            statistics.median(
                tier_1_performance
            )
            if tier_1_performance
            else 50.0
        )

        comparable_risk = (
            statistics.median(
                tier_1_risk
            )
            if tier_1_risk
            else 50.0
        )

        for row in class_rows:
            tier = row["evidence_tier"]

            actual_performance = number(
                row[
                    "historical_performance_score"
                ]
            ) or 0.0

            actual_risk = number(
                row["historical_risk_score"]
            ) or 0.0

            coverage = number(
                row["history_coverage_score"]
            ) or 0.0

            quality = number(
                row["quality_score"]
            ) or 0.0

            valuation = number(
                row["valuation_evidence_score"]
            ) or 0.0

            penalty = number(
                row["uncertainty_penalty"]
            ) or 0.0

            if tier == "TIER_1":
                comparable_score = (
                    0.70 * actual_performance
                    + 0.30 * actual_risk
                )

                base_score = (
                    0.30 * actual_performance
                    + 0.20 * actual_risk
                    + 0.15 * coverage
                    + 0.20 * quality
                    + 0.10 * valuation
                    + 0.05 * comparable_score
                )

            elif tier == "TIER_2":
                comparable_score = (
                    0.65 * comparable_performance
                    + 0.35 * comparable_risk
                )

                base_score = (
                    0.15 * actual_performance
                    + 0.10 * actual_risk
                    + 0.20 * coverage
                    + 0.20 * quality
                    + 0.15 * valuation
                    + 0.20 * comparable_score
                )

            else:
                comparable_score = (
                    0.65 * comparable_performance
                    + 0.35 * comparable_risk
                )

                base_score = (
                    0.10 * coverage
                    + 0.30 * quality
                    + 0.25 * valuation
                    + 0.35 * comparable_score
                )

            universal_score = clamp(
                base_score
                - 0.35 * penalty
            )

            row[
                "comparable_product_score"
            ] = f"{comparable_score:.2f}"

            row[
                "universal_analytical_score"
            ] = f"{universal_score:.2f}"

            class_score_populations[
                product_class
            ].append(universal_score)

    final_rows: list[dict[str, Any]] = []

    for row in preliminary_rows:
        product_class = row["product_class"]

        universal_score = number(
            row["universal_analytical_score"]
        ) or 0.0

        class_percentile = percentile_rank(
            universal_score,
            class_score_populations[
                product_class
            ],
        )

        readiness, reasons = purchase_readiness(
            tier=row["evidence_tier"],
            universal_score=universal_score,
            quality=row["quality_disposition"],
            admission=row["admission_tier"],
            historical_state=row[
                "historical_purchase_state"
            ],
            price_age_days=(
                integer(row["price_age_days"])
                if clean(row["price_age_days"])
                else None
            ),
        )

        existing_reasons = [
            reason
            for reason in reasons
            if reason
        ]

        if row["evidence_tier"] == "TIER_2":
            existing_reasons.append(
                "PROVISIONAL_ANALYSIS_NOT_EQUIVALENT_TO_TIER_1"
            )

        if row["evidence_tier"] == "TIER_3":
            existing_reasons.append(
                "SCORE_RELIES_ON_GOVERNANCE_VALUATION_AND_COMPARABLES"
            )

        row[
            "within_class_analytical_percentile"
        ] = f"{class_percentile:.2f}"

        row[
            "purchase_readiness_state"
        ] = readiness

        row[
            "limitation_reasons"
        ] = "|".join(
            sorted(set(existing_reasons))
        )

        row[
            "analysis_is_forecast"
        ] = "false"

        row[
            "analysis_scope"
        ] = (
            "UNIVERSAL_TIERED_HISTORICAL_AND_CURRENT_EVIDENCE_ANALYSIS"
        )

        final_rows.append(row)

    final_rows.sort(
        key=lambda row: (
            row["evidence_tier"],
            row["product_class"],
            -float(
                row[
                    "universal_analytical_score"
                ]
            ),
            row["canonical_product_name"],
        )
    )

    tier_1_rows = [
        row
        for row in final_rows
        if row["evidence_tier"] == "TIER_1"
    ]

    tier_2_rows = [
        row
        for row in final_rows
        if row["evidence_tier"] == "TIER_2"
    ]

    tier_3_rows = [
        row
        for row in final_rows
        if row["evidence_tier"] == "TIER_3"
    ]

    actionable_rows = [
        row
        for row in final_rows
        if row["purchase_readiness_state"]
        in {
            "PURCHASE_ANALYSIS_ELIGIBLE",
            "MANUAL_PURCHASE_REVIEW",
            "PROVISIONAL_RESEARCH_CANDIDATE",
        }
    ]

    actionable_rows.sort(
        key=lambda row: (
            -float(
                row[
                    "universal_analytical_score"
                ]
            ),
            row["product_class"],
            row["canonical_product_name"],
        )
    )

    write_csv(
        UNIVERSAL_OUTPUT,
        final_rows,
    )

    write_csv(
        TIER_1_OUTPUT,
        tier_1_rows,
    )

    write_csv(
        TIER_2_OUTPUT,
        tier_2_rows,
    )

    write_csv(
        TIER_3_OUTPUT,
        tier_3_rows,
    )

    write_csv(
        ACTIONABLE_OUTPUT,
        actionable_rows,
    )

    tier_counts = Counter(
        row["evidence_tier"]
        for row in final_rows
    )

    status_counts = Counter(
        row["purchase_readiness_state"]
        for row in final_rows
    )

    class_counts = Counter(
        row["product_class"]
        for row in final_rows
    )

    tier_class_counts: dict[
        str,
        Counter[str],
    ] = defaultdict(Counter)

    for row in final_rows:
        tier_class_counts[
            row["evidence_tier"]
        ][row["product_class"]] += 1

    summary = {
        "generated_at": datetime.now().isoformat(),
        "as_of_date": AS_OF_DATE.isoformat(),
        "registry_products": len(
            registry_rows
        ),
        "universal_products_analyzed": len(
            final_rows
        ),
        "tier_counts": dict(
            sorted(tier_counts.items())
        ),
        "purchase_readiness_counts": dict(
            sorted(status_counts.items())
        ),
        "product_class_counts": dict(
            sorted(class_counts.items())
        ),
        "tier_class_counts": {
            tier: dict(
                sorted(counts.items())
            )
            for tier, counts
            in sorted(tier_class_counts.items())
        },
        "actionable_or_research_candidate_rows": len(
            actionable_rows
        ),
        "output_files": {
            "universal": str(
                UNIVERSAL_OUTPUT.relative_to(ROOT)
            ),
            "tier_1": str(
                TIER_1_OUTPUT.relative_to(ROOT)
            ),
            "tier_2": str(
                TIER_2_OUTPUT.relative_to(ROOT)
            ),
            "tier_3": str(
                TIER_3_OUTPUT.relative_to(ROOT)
            ),
            "actionable": str(
                ACTIONABLE_OUTPUT.relative_to(ROOT)
            ),
        },
        "important_interpretation": [
            "All governed products receive an analytical row.",
            "Tier 1 supports full historical analysis.",
            "Tier 2 supports provisional limited-history analysis.",
            "Tier 3 uses current evidence and comparable-product context.",
            "Tier 2 and Tier 3 scores are not equivalent in confidence to Tier 1.",
            "Purchase readiness remains separate from analytical coverage.",
            "No score is a certified forward forecast.",
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

    if len(final_rows) != len(registry_rows):
        raise RuntimeError(
            "Universal output does not match registry population."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
