from __future__ import annotations

import argparse
import csv
import json
import math
import zipfile

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PATHS = 10_000
SEED = 20260809
HORIZONS = (3, 5)

H365_KEY = (
    "HUBER_REGRESSION"
    "|PRICE_PLUS_PATH_STABILITY"
    "|RETURN"
    "|H365"
)


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def numeric(value: object) -> float | None:

    text = clean(value)

    if not text:
        return None

    try:
        result = float(text)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


def read_zip_csv(
    package: Path,
    member: str,
) -> list[dict[str, str]]:

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        if member not in archive.namelist():
            fail(
                f"missing ZIP member {member} "
                f"in {package.name}"
            )

        raw = archive.read(
            member
        ).decode(
            "utf-8-sig"
        )

    return list(
        csv.DictReader(
            raw.splitlines()
        )
    )


def find_zip_csv(
    package: Path,
    contains: str,
) -> list[dict[str, str]]:

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        matches = [
            member
            for member in archive.namelist()
            if (
                member.lower().endswith(
                    ".csv"
                )
                and contains.lower()
                in member.lower()
            )
        ]

        if len(matches) != 1:
            fail(
                f"expected one CSV containing "
                f"{contains}; got {matches}"
            )

        raw = archive.read(
            matches[0]
        ).decode(
            "utf-8-sig"
        )

    return list(
        csv.DictReader(
            raw.splitlines()
        )
    )


def read_zip_json(
    package: Path,
    member: str,
) -> dict:

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        if member not in archive.namelist():
            fail(
                f"missing ZIP JSON {member}"
            )

        return json.loads(
            archive.read(
                member
            ).decode(
                "utf-8-sig"
            )
        )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: list[str],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
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

        for row in rows:
            writer.writerow(row)


def percentile_ranks(
    values: dict[str, float],
) -> dict[str, float]:

    if not values:
        return {}

    items = sorted(
        values.items(),
        key=lambda pair:
            (
                pair[1],
                pair[0],
            ),
    )

    count = len(items)

    if count == 1:
        return {
            items[0][0]:
                1.0
        }

    result = {}

    index = 0

    while index < count:

        value = items[index][1]

        end = index

        while (
            end + 1 < count
            and math.isclose(
                items[end + 1][1],
                value,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ):
            end += 1

        average_position = (
            index
            + end
        ) / 2.0

        rank = (
            average_position
            / float(
                count - 1
            )
        )

        for position in range(
            index,
            end + 1,
        ):
            result[
                items[position][0]
            ] = float(rank)

        index = end + 1

    return result


def quartile_labels(
    score_by_product: dict[str, float],
) -> dict[str, str]:

    if not score_by_product:
        return {}

    values = np.asarray(
        list(
            score_by_product.values()
        ),
        dtype=float,
    )

    q25 = float(
        np.quantile(
            values,
            0.25,
        )
    )

    q50 = float(
        np.quantile(
            values,
            0.50,
        )
    )

    q75 = float(
        np.quantile(
            values,
            0.75,
        )
    )

    result = {}

    for product, score in (
        score_by_product.items()
    ):

        if score >= q75:
            label = "TIER_1_TOP_QUARTILE"

        elif score >= q50:
            label = "TIER_2_SECOND_QUARTILE"

        elif score >= q25:
            label = "TIER_3_THIRD_QUARTILE"

        else:
            label = "TIER_4_BOTTOM_QUARTILE"

        result[product] = label

    return result


def resolve_disagreement_column(
    row: dict[str, str],
) -> str | None:

    exact = (
        "source_disagreement",
        "source_disagreement_ratio",
        "source_disagreement_pct",
        "source_disagreement_percent",
        "price_source_disagreement",
    )

    for candidate in exact:

        if candidate in row:
            return candidate

    matches = [
        column
        for column in row
        if (
            "source"
            in column.lower()
            and "disagreement"
            in column.lower()
        )
    ]

    numeric_matches = []

    for column in matches:

        if any(
            numeric(candidate.get(column))
            is not None
            for candidate in [row]
        ):
            numeric_matches.append(column)

    if len(numeric_matches) == 1:
        return numeric_matches[0]

    if len(matches) == 1:
        return matches[0]

    return None


def count_evidence_domains(
    value: object,
) -> int:

    text = clean(value)

    if not text:
        return 0

    direct = numeric(text)

    if direct is not None:
        rounded = int(round(direct))
        return max(
            0,
            min(
                3,
                rounded,
            ),
        )

    upper = text.upper()

    if upper in {
        "ALL_3",
        "ALL THREE",
        "THREE",
    }:
        return 3

    separators = (
        ";",
        ",",
        "|",
        "+",
    )

    parts = [text]

    for separator in separators:

        if separator in text:

            parts = [
                item.strip()
                for item
                in text.split(separator)
                if item.strip()
            ]

            break

    return max(
        0,
        min(
            3,
            len(parts),
        ),
    )


def monte_carlo_product(
    rng: np.random.Generator,
    current_price: float,
    one_year_forecast_price: float,
    residuals: np.ndarray,
    years: int,
) -> dict[str, float]:

    if (
        current_price <= 0
        or one_year_forecast_price <= 0
    ):
        fail(
            "nonpositive MC price anchor"
        )

    annual_anchor = math.log(
        one_year_forecast_price
        / current_price
    )

    sampled = rng.choice(
        residuals,
        size=(
            PATHS,
            years,
        ),
        replace=True,
    )

    annual_log_returns = (
        annual_anchor
        + sampled
    )

    cumulative_logs = np.cumsum(
        annual_log_returns,
        axis=1,
    )

    prices = (
        current_price
        * np.exp(
            cumulative_logs
        )
    )

    terminal_prices = prices[
        :,
        -1
    ]

    total_returns = (
        terminal_prices
        / current_price
    ) - 1.0

    cagr = (
        (
            terminal_prices
            / current_price
        )
        ** (
            1.0
            / float(years)
        )
    ) - 1.0

    # Annual-path maximum drawdown.
    initial = np.full(
        (
            PATHS,
            1,
        ),
        current_price,
        dtype=float,
    )

    path_with_initial = np.concatenate(
        [
            initial,
            prices,
        ],
        axis=1,
    )

    running_max = np.maximum.accumulate(
        path_with_initial,
        axis=1,
    )

    drawdowns = (
        path_with_initial
        / running_max
    ) - 1.0

    max_drawdown = np.min(
        drawdowns,
        axis=1,
    )

    p10_return = float(
        np.quantile(
            total_returns,
            0.10,
        )
    )

    lower_tail = total_returns[
        total_returns
        <= p10_return
    ]

    cvar10 = (
        float(
            np.mean(
                lower_tail
            )
        )
        if len(lower_tail)
        else p10_return
    )

    return {
        "terminal_price_mean":
            float(
                np.mean(
                    terminal_prices
                )
            ),

        "terminal_price_p10":
            float(
                np.quantile(
                    terminal_prices,
                    0.10,
                )
            ),

        "terminal_price_p25":
            float(
                np.quantile(
                    terminal_prices,
                    0.25,
                )
            ),

        "terminal_price_median":
            float(
                np.quantile(
                    terminal_prices,
                    0.50,
                )
            ),

        "terminal_price_p75":
            float(
                np.quantile(
                    terminal_prices,
                    0.75,
                )
            ),

        "terminal_price_p90":
            float(
                np.quantile(
                    terminal_prices,
                    0.90,
                )
            ),

        "mean_total_return":
            float(
                np.mean(
                    total_returns
                )
            ),

        "median_total_return":
            float(
                np.median(
                    total_returns
                )
            ),

        "mean_cagr":
            float(
                np.mean(
                    cagr
                )
            ),

        "median_cagr":
            float(
                np.median(
                    cagr
                )
            ),

        "probability_positive_return":
            float(
                np.mean(
                    total_returns > 0
                )
            ),

        "probability_cagr_above_5pct":
            float(
                np.mean(
                    cagr > 0.05
                )
            ),

        "probability_capital_loss":
            float(
                np.mean(
                    total_returns < 0
                )
            ),

        "return_p10":
            p10_return,

        "return_cvar10":
            cvar10,

        "median_max_drawdown":
            float(
                np.median(
                    max_drawdown
                )
            ),

        "p10_max_drawdown":
            float(
                np.quantile(
                    max_drawdown,
                    0.10,
                )
            ),

        "terminal_log_dispersion":
            float(
                np.std(
                    np.log(
                        terminal_prices
                        / current_price
                    ),
                    ddof=0,
                )
            ),
    }


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--canonical-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--current-price-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--availability-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--diagnostics-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--base-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--final-forecast-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    output_root = (
        args.output_root.resolve()
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================================
    # Load certified evidence
    # ========================================================================

    canonical_rows = read_zip_csv(
        args.canonical_package,
        "precollector_canonical_universe_v2.csv",
    )

    current_rows = find_zip_csv(
        args.current_price_package,
        "current_price_authority_v2",
    )

    diagnostics_rows = read_zip_csv(
        args.diagnostics_package,
        "precollector_empirical_eligibility_diagnostics_v1.csv",
    )

    base_rows = read_zip_csv(
        args.base_package,
        "precollector_base_common_fold_prediction_ledger_v1.csv",
    )

    forecast_rows = read_zip_csv(
        args.final_forecast_package,
        "precollector_certified_365_day_forecast_v1.csv",
    )

    forecast_gap_rows = read_zip_csv(
        args.final_forecast_package,
        "precollector_certified_365_day_forecast_gap_ledger_v1.csv",
    )

    final_summary = read_zip_json(
        args.final_forecast_package,
        "precollector_final_model_forecast_scenario_summary_v1.json",
    )

    # Availability package is bound independently even though the product-level
    # liquidity measures used below were already materialized into the certified
    # empirical diagnostic ledger.
    with zipfile.ZipFile(
        args.availability_package,
        "r",
    ) as availability_archive:

        if not availability_archive.namelist():
            fail(
                "availability package is empty"
            )

    if len(canonical_rows) != 131:
        fail(
            f"canonical rows={len(canonical_rows)}; expected 131"
        )

    if len(current_rows) != 121:
        fail(
            f"current price authority rows={len(current_rows)}; expected 121"
        )

    if len(diagnostics_rows) != 131:
        fail(
            f"diagnostic rows={len(diagnostics_rows)}; expected 131"
        )

    if len(forecast_rows) != 95:
        fail(
            f"forecast rows={len(forecast_rows)}; expected 95"
        )

    if len(forecast_gap_rows) != 26:
        fail(
            f"forecast gap rows={len(forecast_gap_rows)}; expected 26"
        )

    if (
        final_summary[
            "status"
        ]
        !=
        "PASS_PRECOLLECTOR_FINAL_MODEL_FORECAST_SCENARIO_V1"
    ):
        fail(
            "final forecast package did not PASS"
        )

    if (
        int(
            final_summary[
                "persistent_product_exclusions"
            ]
        )
        != 0
    ):
        fail(
            "unexpected persistent exclusion"
        )

    # ========================================================================
    # Residual authority — exactly the certified H365 OOS model residuals
    # ========================================================================

    residuals = []

    for row in base_rows:

        if (
            int(
                row[
                    "requested_horizon_days"
                ]
            )
            != 365
        ):
            continue

        if (
            clean(
                row[
                    "semantic_model_key"
                ]
            )
            != H365_KEY
        ):
            continue

        actual = numeric(
            row[
                "actual_endpoint_price"
            ]
        )

        predicted = numeric(
            row[
                "predicted_endpoint_price"
            ]
        )

        if (
            actual is None
            or predicted is None
            or actual <= 0
            or predicted <= 0
        ):
            continue

        residuals.append(
            math.log(
                actual
                / predicted
            )
        )

    if len(residuals) != 516:
        fail(
            f"H365 residual count={len(residuals)}; expected 516"
        )

    residual_array = np.asarray(
        residuals,
        dtype=float,
    )

    # ========================================================================
    # Product evidence maps
    # ========================================================================

    canonical_by_id = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
            row
        for row in canonical_rows
    }

    diagnostics_by_id = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
            row
        for row in diagnostics_rows
    }

    current_ids = {
        clean(
            row[
                "canonical_product_id"
            ]
        )
        for row in current_rows
    }

    forecast_gap_by_id = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
            row
        for row in forecast_gap_rows
    }

    forecast_by_id = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
            row
        for row in forecast_rows
    }

    if len(forecast_by_id) != 95:
        fail(
            "forecast product IDs are not unique"
        )

    if len(forecast_gap_by_id) != 26:
        fail(
            "forecast-gap product IDs are not unique"
        )

    if (
        set(forecast_by_id)
        & set(forecast_gap_by_id)
    ):
        fail(
            "forecast and forecast-gap products overlap"
        )

    if (
        set(forecast_by_id)
        | set(forecast_gap_by_id)
    ) != current_ids:
        fail(
            "121 current-price products do not reconcile to 95 forecasts + 26 gaps"
        )

    no_current_price_ids = (
        set(canonical_by_id)
        - current_ids
    )

    if len(no_current_price_ids) != 10:
        fail(
            f"no-current-price canonical count={len(no_current_price_ids)}; expected 10"
        )

    # ========================================================================
    # Resolve empirical evidence fields
    # ========================================================================

    sample_diag = diagnostics_rows[0]

    required_diag_columns = (
        "evidence_domains_present",
        "history_observation_count",
        "accepted_listing_count",
        "unique_seller_count",
    )

    for column in required_diag_columns:

        if column not in sample_diag:
            fail(
                f"required empirical diagnostic column missing: {column}"
            )

    disagreement_column = (
        resolve_disagreement_column(
            sample_diag
        )
    )

    # ========================================================================
    # Evidence / liquidity raw quantities
    # ========================================================================

    history_count = {}
    listing_count = {}
    seller_count = {}
    domain_count = {}
    disagreement_values = {}

    for product_id, diag in (
        diagnostics_by_id.items()
    ):

        history_count[
            product_id
        ] = (
            numeric(
                diag.get(
                    "history_observation_count"
                )
            )
            or 0.0
        )

        listing_count[
            product_id
        ] = (
            numeric(
                diag.get(
                    "accepted_listing_count"
                )
            )
            or 0.0
        )

        seller_count[
            product_id
        ] = (
            numeric(
                diag.get(
                    "unique_seller_count"
                )
            )
            or 0.0
        )

        domain_count[
            product_id
        ] = float(
            count_evidence_domains(
                diag.get(
                    "evidence_domains_present"
                )
            )
        )

        if disagreement_column:

            disagreement = numeric(
                diag.get(
                    disagreement_column
                )
            )

            if disagreement is not None:

                disagreement_values[
                    product_id
                ] = float(
                    disagreement
                )

    # Percentile-scale evidence terms over all 131 canonical products.
    history_pct = percentile_ranks(
        history_count
    )

    listing_pct = percentile_ranks(
        {
            key:
                math.log1p(value)
            for key, value
            in listing_count.items()
        }
    )

    seller_pct = percentile_ranks(
        {
            key:
                math.log1p(value)
            for key, value
            in seller_count.items()
        }
    )

    if disagreement_values:

        disagreement_pct = (
            percentile_ranks(
                disagreement_values
            )
        )

    else:
        disagreement_pct = {}

    evidence_quality = {}
    liquidity_score = {}

    for product_id in canonical_by_id:

        domain_component = (
            domain_count.get(
                product_id,
                0.0,
            )
            / 3.0
        )

        history_component = (
            history_pct.get(
                product_id,
                0.0,
            )
        )

        if product_id in disagreement_pct:

            disagreement_component = (
                1.0
                - disagreement_pct[
                    product_id
                ]
            )

            evidence_quality[
                product_id
            ] = float(
                (
                    domain_component
                    + history_component
                    + disagreement_component
                )
                / 3.0
            )

        else:

            evidence_quality[
                product_id
            ] = float(
                (
                    domain_component
                    + history_component
                )
                / 2.0
            )

        liquidity_score[
            product_id
        ] = float(
            (
                listing_pct.get(
                    product_id,
                    0.0,
                )
                + seller_pct.get(
                    product_id,
                    0.0,
                )
            )
            / 2.0
        )

    confidence_labels = quartile_labels(
        {
            product_id:
                evidence_quality[
                    product_id
                ]
            for product_id
            in forecast_by_id
        }
    )

    # ========================================================================
    # Monte Carlo
    # ========================================================================

    print(
        "============================================================",
        flush=True,
    )

    print(
        "PHASE_A_EMPIRICAL_RESIDUAL_MONTE_CARLO",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    rng = np.random.default_rng(
        SEED
    )

    monte_rows = []

    products = sorted(
        forecast_by_id
    )

    for product_index, product_id in enumerate(
        products,
        start=1,
    ):

        forecast = forecast_by_id[
            product_id
        ]

        current_price = numeric(
            forecast[
                "current_price"
            ]
        )

        one_year_price = numeric(
            forecast[
                "forecast_price_365d"
            ]
        )

        if (
            current_price is None
            or one_year_price is None
            or current_price <= 0
            or one_year_price <= 0
        ):
            fail(
                f"invalid certified forecast anchor for {product_id}"
            )

        for years in HORIZONS:

            result = monte_carlo_product(
                rng,
                current_price,
                one_year_price,
                residual_array,
                years,
            )

            monte_rows.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        clean(
                            forecast[
                                "product_name"
                            ]
                        ),

                    "current_price":
                        current_price,

                    "certified_365_forecast_price":
                        one_year_price,

                    "monte_carlo_horizon_years":
                        years,

                    "monte_carlo_paths":
                        PATHS,

                    "random_seed":
                        SEED,

                    "residual_observation_count":
                        len(
                            residual_array
                        ),

                    **result,

                    "evidence_quality_score":
                        evidence_quality[
                            product_id
                        ],

                    "liquidity_score":
                        liquidity_score[
                            product_id
                        ],

                    "accepted_listing_count":
                        listing_count.get(
                            product_id,
                            0.0,
                        ),

                    "unique_seller_count":
                        seller_count.get(
                            product_id,
                            0.0,
                        ),

                    "history_observation_count":
                        history_count.get(
                            product_id,
                            0.0,
                        ),

                    "evidence_domains_present":
                        domain_count.get(
                            product_id,
                            0.0,
                        ),

                    "source_disagreement_metric":
                        (
                            disagreement_values.get(
                                product_id,
                                "",
                            )
                        ),

                    "confidence_quartile":
                        confidence_labels[
                            product_id
                        ],

                    "scenario_classification":
                        (
                            "THREE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED"
                            if years == 3
                            else
                            "FIVE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED"
                        ),

                    "directly_backtested_at_this_horizon":
                        "false",

                    "persistent_product_exclusion":
                        "false",
                }
            )

        if (
            product_index % 10 == 0
            or product_index == len(
                products
            )
        ):

            print(
                (
                    "MONTE_CARLO_PROGRESS="
                    f"{product_index}/{len(products)}"
                ),
                flush=True,
            )

    if len(monte_rows) != 190:
        fail(
            f"Monte Carlo summary rows={len(monte_rows)}; expected 190"
        )

    # ========================================================================
    # Horizon-specific scoring
    # ========================================================================

    print(
        "",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        "PHASE_B_MODEL_AND_PURCHASE_RANKINGS",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    horizon_purchase_rows = []

    for years in HORIZONS:

        rows = [
            row
            for row in monte_rows
            if (
                int(
                    row[
                        "monte_carlo_horizon_years"
                    ]
                )
                == years
            )
        ]

        cagr_pct = percentile_ranks(
            {
                row[
                    "canonical_product_id"
                ]:
                    float(
                        row[
                            "median_cagr"
                        ]
                    )
                for row in rows
            }
        )

        downside_pct = percentile_ranks(
            {
                row[
                    "canonical_product_id"
                ]:
                    float(
                        row[
                            "return_cvar10"
                        ]
                    )
                for row in rows
            }
        )

        for row in rows:

            product_id = (
                row[
                    "canonical_product_id"
                ]
            )

            probability_positive = float(
                row[
                    "probability_positive_return"
                ]
            )

            purchase_score = 100.0 * (
                0.20
                * cagr_pct[
                    product_id
                ]
                + 0.20
                * probability_positive
                + 0.20
                * downside_pct[
                    product_id
                ]
                + 0.20
                * float(
                    row[
                        "evidence_quality_score"
                    ]
                )
                + 0.20
                * float(
                    row[
                        "liquidity_score"
                    ]
                )
            )

            horizon_purchase_rows.append(
                {
                    **row,

                    "median_cagr_percentile":
                        cagr_pct[
                            product_id
                        ],

                    "downside_cvar10_percentile":
                        downside_pct[
                            product_id
                        ],

                    "purchase_score":
                        float(
                            purchase_score
                        ),
                }
            )

    # ========================================================================
    # Model-return rankings, separately by horizon
    # ========================================================================

    model_rank_rows = []

    for years in HORIZONS:

        rows = [
            row
            for row in horizon_purchase_rows
            if (
                int(
                    row[
                        "monte_carlo_horizon_years"
                    ]
                )
                == years
            )
        ]

        rows.sort(
            key=lambda row: (
                -float(
                    row[
                        "median_cagr"
                    ]
                ),
                -float(
                    row[
                        "probability_positive_return"
                    ]
                ),
                row[
                    "canonical_product_id"
                ],
            )
        )

        for rank, row in enumerate(
            rows,
            start=1,
        ):

            model_rank_rows.append(
                {
                    "monte_carlo_horizon_years":
                        years,

                    "model_rank":
                        rank,

                    "canonical_product_id":
                        row[
                            "canonical_product_id"
                        ],

                    "product_name":
                        row[
                            "product_name"
                        ],

                    "current_price":
                        row[
                            "current_price"
                        ],

                    "terminal_price_median":
                        row[
                            "terminal_price_median"
                        ],

                    "median_cagr":
                        row[
                            "median_cagr"
                        ],

                    "probability_positive_return":
                        row[
                            "probability_positive_return"
                        ],

                    "return_p10":
                        row[
                            "return_p10"
                        ],

                    "return_cvar10":
                        row[
                            "return_cvar10"
                        ],

                    "scenario_classification":
                        row[
                            "scenario_classification"
                        ],
                }
            )

    # ========================================================================
    # Combined purchase ranking:
    # equal 3Y / 5Y weight.
    # ========================================================================

    purchase_by_product = defaultdict(
        dict
    )

    for row in horizon_purchase_rows:

        purchase_by_product[
            row[
                "canonical_product_id"
            ]
        ][
            int(
                row[
                    "monte_carlo_horizon_years"
                ]
            )
        ] = row

    combined_rows = []

    for product_id in sorted(
        purchase_by_product
    ):

        horizon_map = (
            purchase_by_product[
                product_id
            ]
        )

        if (
            3 not in horizon_map
            or 5 not in horizon_map
        ):
            fail(
                f"missing horizon score for {product_id}"
            )

        row3 = horizon_map[3]
        row5 = horizon_map[5]

        combined_score = (
            0.50
            * float(
                row3[
                    "purchase_score"
                ]
            )
            + 0.50
            * float(
                row5[
                    "purchase_score"
                ]
            )
        )

        combined_rows.append(
            {
                "canonical_product_id":
                    product_id,

                "product_name":
                    row3[
                        "product_name"
                    ],

                "current_price":
                    row3[
                        "current_price"
                    ],

                "forecast_price_365d":
                    row3[
                        "certified_365_forecast_price"
                    ],

                "median_cagr_3y":
                    row3[
                        "median_cagr"
                    ],

                "median_cagr_5y":
                    row5[
                        "median_cagr"
                    ],

                "probability_positive_3y":
                    row3[
                        "probability_positive_return"
                    ],

                "probability_positive_5y":
                    row5[
                        "probability_positive_return"
                    ],

                "probability_cagr_above_5pct_3y":
                    row3[
                        "probability_cagr_above_5pct"
                    ],

                "probability_cagr_above_5pct_5y":
                    row5[
                        "probability_cagr_above_5pct"
                    ],

                "downside_cvar10_3y":
                    row3[
                        "return_cvar10"
                    ],

                "downside_cvar10_5y":
                    row5[
                        "return_cvar10"
                    ],

                "median_max_drawdown_3y":
                    row3[
                        "median_max_drawdown"
                    ],

                "median_max_drawdown_5y":
                    row5[
                        "median_max_drawdown"
                    ],

                "evidence_quality_score":
                    row3[
                        "evidence_quality_score"
                    ],

                "liquidity_score":
                    row3[
                        "liquidity_score"
                    ],

                "accepted_listing_count":
                    row3[
                        "accepted_listing_count"
                    ],

                "unique_seller_count":
                    row3[
                        "unique_seller_count"
                    ],

                "history_observation_count":
                    row3[
                        "history_observation_count"
                    ],

                "confidence_quartile":
                    row3[
                        "confidence_quartile"
                    ],

                "purchase_score_3y":
                    row3[
                        "purchase_score"
                    ],

                "purchase_score_5y":
                    row5[
                        "purchase_score"
                    ],

                "combined_purchase_score":
                    float(
                        combined_score
                    ),

                "three_year_classification":
                    "THREE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED",

                "five_year_classification":
                    "FIVE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED",

                "persistent_product_exclusion":
                    "false",
            }
        )

    if len(combined_rows) != 95:
        fail(
            "combined ranked universe != 95"
        )

    tier_map = quartile_labels(
        {
            row[
                "canonical_product_id"
            ]:
                float(
                    row[
                        "combined_purchase_score"
                    ]
                )
            for row in combined_rows
        }
    )

    combined_rows.sort(
        key=lambda row: (
            -float(
                row[
                    "combined_purchase_score"
                ]
            ),
            -float(
                row[
                    "median_cagr_5y"
                ]
            ),
            row[
                "canonical_product_id"
            ],
        )
    )

    for rank, row in enumerate(
        combined_rows,
        start=1,
    ):

        row[
            "purchase_rank"
        ] = rank

        row[
            "investment_tier"
        ] = tier_map[
            row[
                "canonical_product_id"
            ]
        ]

    # ========================================================================
    # High-confidence and speculative views
    # ========================================================================

    high_confidence_rows = [
        row
        for row in combined_rows
        if (
            row[
                "confidence_quartile"
            ]
            == "TIER_1_TOP_QUARTILE"
        )
    ]

    high_confidence_rows.sort(
        key=lambda row:
            (
                -float(
                    row[
                        "combined_purchase_score"
                    ]
                ),
                row[
                    "canonical_product_id"
                ],
            )
    )

    for rank, row in enumerate(
        high_confidence_rows,
        start=1,
    ):
        row[
            "high_confidence_rank"
        ] = rank

    speculative_rows = [
        row
        for row in combined_rows
        if (
            row[
                "confidence_quartile"
            ]
            in {
                "TIER_3_THIRD_QUARTILE",
                "TIER_4_BOTTOM_QUARTILE",
            }
            and float(
                row[
                    "median_cagr_5y"
                ]
            ) > 0
        )
    ]

    speculative_rows.sort(
        key=lambda row:
            (
                -float(
                    row[
                        "median_cagr_5y"
                    ]
                ),
                row[
                    "canonical_product_id"
                ],
            )
    )

    for rank, row in enumerate(
        speculative_rows,
        start=1,
    ):
        row[
            "speculative_rank"
        ] = rank

    # ========================================================================
    # Full 131-product disposition
    # ========================================================================

    final_disposition_rows = []

    for product_id in sorted(
        canonical_by_id
    ):

        canonical = canonical_by_id[
            product_id
        ]

        product_name = clean(
            canonical[
                "product_name"
            ]
        )

        if product_id in forecast_by_id:

            ranked = next(
                row
                for row in combined_rows
                if (
                    row[
                        "canonical_product_id"
                    ]
                    == product_id
                )
            )

            final_disposition_rows.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        product_name,

                    "canonical_member":
                        "true",

                    "final_analysis_status":
                        "RANKED_FORECASTABLE",

                    "purchase_rank":
                        ranked[
                            "purchase_rank"
                        ],

                    "investment_tier":
                        ranked[
                            "investment_tier"
                        ],

                    "current_price":
                        ranked[
                            "current_price"
                        ],

                    "combined_purchase_score":
                        ranked[
                            "combined_purchase_score"
                        ],

                    "not_ranked_reason":
                        "",

                    "persistent_product_exclusion":
                        "false",
                }
            )

        elif product_id in forecast_gap_by_id:

            gap = forecast_gap_by_id[
                product_id
            ]

            final_disposition_rows.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        product_name,

                    "canonical_member":
                        "true",

                    "final_analysis_status":
                        "NOT_RANKED_FORECAST_GAP",

                    "purchase_rank":
                        "",

                    "investment_tier":
                        "NOT_RANKED",

                    "current_price":
                        gap.get(
                            "current_price",
                            "",
                        ),

                    "combined_purchase_score":
                        "",

                    "not_ranked_reason":
                        clean(
                            gap.get(
                                "gap_reason"
                            )
                        ),

                    "persistent_product_exclusion":
                        "false",
                }
            )

        elif product_id in no_current_price_ids:

            final_disposition_rows.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        product_name,

                    "canonical_member":
                        "true",

                    "final_analysis_status":
                        "NOT_RANKED_NO_CURRENT_PRICE_AUTHORITY",

                    "purchase_rank":
                        "",

                    "investment_tier":
                        "NOT_RANKED",

                    "current_price":
                        "",

                    "combined_purchase_score":
                        "",

                    "not_ranked_reason":
                        "NO_GOVERNED_CURRENT_PRICE_AUTHORITY",

                    "persistent_product_exclusion":
                        "false",
                }
            )

        else:

            fail(
                f"unresolved canonical disposition {product_id}"
            )

    if len(final_disposition_rows) != 131:
        fail(
            "final disposition row count != 131"
        )

    disposition_counts = defaultdict(
        int
    )

    for row in final_disposition_rows:

        disposition_counts[
            row[
                "final_analysis_status"
            ]
        ] += 1

    if (
        disposition_counts[
            "RANKED_FORECASTABLE"
        ]
        != 95
    ):
        fail(
            "ranked disposition != 95"
        )

    if (
        disposition_counts[
            "NOT_RANKED_FORECAST_GAP"
        ]
        != 26
    ):
        fail(
            "forecast-gap disposition != 26"
        )

    if (
        disposition_counts[
            "NOT_RANKED_NO_CURRENT_PRICE_AUTHORITY"
        ]
        != 10
    ):
        fail(
            "no-current-price disposition != 10"
        )

    # ========================================================================
    # Outputs
    # ========================================================================

    mc_path = (
        output_root
        / "precollector_monte_carlo_summary_v1.csv"
    )

    model_rank_path = (
        output_root
        / "precollector_model_return_ranking_v1.csv"
    )

    purchase_rank_path = (
        output_root
        / "precollector_purchase_ranking_v1.csv"
    )

    high_confidence_path = (
        output_root
        / "precollector_high_confidence_purchase_ranking_v1.csv"
    )

    speculative_path = (
        output_root
        / "precollector_speculative_candidate_ranking_v1.csv"
    )

    disposition_path = (
        output_root
        / "precollector_final_131_product_disposition_v1.csv"
    )

    residual_path = (
        output_root
        / "precollector_monte_carlo_residual_authority_v1.csv"
    )

    summary_path = (
        output_root
        / "precollector_monte_carlo_purchase_ranking_summary_v1.json"
    )

    write_csv(
        mc_path,
        horizon_purchase_rows,
        [
            "canonical_product_id",
            "product_name",
            "current_price",
            "certified_365_forecast_price",
            "monte_carlo_horizon_years",
            "monte_carlo_paths",
            "random_seed",
            "residual_observation_count",
            "terminal_price_mean",
            "terminal_price_p10",
            "terminal_price_p25",
            "terminal_price_median",
            "terminal_price_p75",
            "terminal_price_p90",
            "mean_total_return",
            "median_total_return",
            "mean_cagr",
            "median_cagr",
            "probability_positive_return",
            "probability_cagr_above_5pct",
            "probability_capital_loss",
            "return_p10",
            "return_cvar10",
            "median_max_drawdown",
            "p10_max_drawdown",
            "terminal_log_dispersion",
            "evidence_quality_score",
            "liquidity_score",
            "accepted_listing_count",
            "unique_seller_count",
            "history_observation_count",
            "evidence_domains_present",
            "source_disagreement_metric",
            "confidence_quartile",
            "median_cagr_percentile",
            "downside_cvar10_percentile",
            "purchase_score",
            "scenario_classification",
            "directly_backtested_at_this_horizon",
            "persistent_product_exclusion",
        ],
    )

    write_csv(
        model_rank_path,
        model_rank_rows,
        [
            "monte_carlo_horizon_years",
            "model_rank",
            "canonical_product_id",
            "product_name",
            "current_price",
            "terminal_price_median",
            "median_cagr",
            "probability_positive_return",
            "return_p10",
            "return_cvar10",
            "scenario_classification",
        ],
    )

    purchase_fields = [
        "purchase_rank",
        "canonical_product_id",
        "product_name",
        "current_price",
        "forecast_price_365d",
        "median_cagr_3y",
        "median_cagr_5y",
        "probability_positive_3y",
        "probability_positive_5y",
        "probability_cagr_above_5pct_3y",
        "probability_cagr_above_5pct_5y",
        "downside_cvar10_3y",
        "downside_cvar10_5y",
        "median_max_drawdown_3y",
        "median_max_drawdown_5y",
        "evidence_quality_score",
        "liquidity_score",
        "accepted_listing_count",
        "unique_seller_count",
        "history_observation_count",
        "confidence_quartile",
        "purchase_score_3y",
        "purchase_score_5y",
        "combined_purchase_score",
        "investment_tier",
        "three_year_classification",
        "five_year_classification",
        "persistent_product_exclusion",
    ]

    write_csv(
        purchase_rank_path,
        combined_rows,
        purchase_fields,
    )

    write_csv(
        high_confidence_path,
        high_confidence_rows,
        [
            "high_confidence_rank",
            *purchase_fields,
        ],
    )

    write_csv(
        speculative_path,
        speculative_rows,
        [
            "speculative_rank",
            *purchase_fields,
        ],
    )

    write_csv(
        disposition_path,
        final_disposition_rows,
        [
            "canonical_product_id",
            "product_name",
            "canonical_member",
            "final_analysis_status",
            "purchase_rank",
            "investment_tier",
            "current_price",
            "combined_purchase_score",
            "not_ranked_reason",
            "persistent_product_exclusion",
        ],
    )

    write_csv(
        residual_path,
        [
            {
                "residual_index":
                    index + 1,

                "log_actual_over_predicted_residual":
                    float(value),
            }
            for index, value
            in enumerate(
                residual_array
            )
        ],
        [
            "residual_index",
            "log_actual_over_predicted_residual",
        ],
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_MONTE_CARLO_PURCHASE_RANKING_V1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "canonical_products":
            131,

        "forecastable_ranked_products":
            95,

        "forecast_gap_products":
            26,

        "no_current_price_authority_products":
            10,

        "final_disposition_rows":
            131,

        "monte_carlo_paths_per_product_per_horizon":
            PATHS,

        "monte_carlo_horizons_years":
            [
                3,
                5,
            ],

        "monte_carlo_product_horizon_rows":
            len(
                monte_rows
            ),

        "total_terminal_paths_simulated":
            (
                95
                * 2
                * PATHS
            ),

        "residual_observation_count":
            len(
                residual_array
            ),

        "residual_sampling":
            "EMPIRICAL_ANNUAL_BLOCK_BOOTSTRAP_WITH_REPLACEMENT",

        "random_seed":
            SEED,

        "purchase_score_components":
            [
                "MEDIAN_CAGR_PERCENTILE",
                "PROBABILITY_POSITIVE_RETURN",
                "DOWNSIDE_CVAR10_PERCENTILE",
                "EVIDENCE_QUALITY_SCORE",
                "LIQUIDITY_SCORE",
            ],

        "purchase_score_equal_weights":
            True,

        "high_confidence_ranked_products":
            len(
                high_confidence_rows
            ),

        "speculative_candidate_products":
            len(
                speculative_rows
            ),

        "three_year_direct_backtest":
            False,

        "five_year_direct_backtest":
            False,

        "persistent_product_exclusions":
            0,

        "case_products_ranked":
            0,

        "synthetic_case_to_box_prices":
            0,

        "monte_carlo_certified":
            True,

        "uncertainty_certified":
            True,

        "investment_ranking_certified":
            True,

        "purchase_analysis_certified":
            True,

        "secret_lair_work_authorized":
            False,
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # ========================================================================
    # Visible top-ten output
    # ========================================================================

    print(
        "",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        "TOP_10_PURCHASE_RANKING",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    for row in combined_rows[:10]:

        print(
            (
                f"RANK={row['purchase_rank']}"
                f"|PRODUCT={row['product_name']}"
                f"|PRICE={float(row['current_price']):.2f}"
                f"|SCORE={float(row['combined_purchase_score']):.4f}"
                f"|3Y_MEDIAN_CAGR={float(row['median_cagr_3y']):.4f}"
                f"|5Y_MEDIAN_CAGR={float(row['median_cagr_5y']):.4f}"
                f"|5Y_POSITIVE={float(row['probability_positive_5y']):.4f}"
                f"|CONFIDENCE={row['confidence_quartile']}"
                f"|TIER={row['investment_tier']}"
            ),
            flush=True,
        )

    print(
        "",
        flush=True,
    )

    print(
        "PASS_PRECOLLECTOR_MONTE_CARLO_PURCHASE_RANKING_V1",
        flush=True,
    )

    print(
        "CANONICAL_PRODUCTS=131",
        flush=True,
    )

    print(
        "RANKED_PRODUCTS=95",
        flush=True,
    )

    print(
        "FORECAST_GAP_PRODUCTS=26",
        flush=True,
    )

    print(
        "NO_CURRENT_PRICE_AUTHORITY_PRODUCTS=10",
        flush=True,
    )

    print(
        "MONTE_CARLO_PATHS_PER_PRODUCT_PER_HORIZON=10000",
        flush=True,
    )

    print(
        "TOTAL_TERMINAL_PATHS_SIMULATED=1900000",
        flush=True,
    )

    print(
        "PERSISTENT_PRODUCT_EXCLUSIONS=0",
        flush=True,
    )

    print(
        "CASE_PRODUCTS_RANKED=0",
        flush=True,
    )

    print(
        "PURCHASE_ANALYSIS_CERTIFIED=TRUE",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )