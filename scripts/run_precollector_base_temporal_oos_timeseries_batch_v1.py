from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import zipfile

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr


MODELS = (
    "LAST_VALUE",
    "DRIFT",
    "LOG_DRIFT",
    "ROBUST_TREND",
    "EXPONENTIAL_SMOOTHING",
)

HORIZONS = (
    90,
    180,
    365,
)

FEATURE_VARIANTS = (
    "PRICE_ONLY",
    "PRICE_PLUS_AGE",
    "PRICE_PLUS_PATH_STABILITY",
)

TARGETS = (
    "RAW_PRICE_CHANGE",
    "LOG_PRICE_CHANGE",
    "RETURN",
    "ANNUALIZED_RETURN_WHERE_DEFINED",
)


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def clean(value: object) -> str:
    return str(
        value or ""
    ).strip()


def parse_date(value: object) -> date:
    return date.fromisoformat(
        clean(value)[:10]
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:

        for block in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                block
            )

    return digest.hexdigest()


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
                f"missing ZIP member: {member}"
            )

        text = archive.read(
            member
        ).decode(
            "utf-8-sig"
        )

    return list(
        csv.DictReader(
            text.splitlines()
        )
    )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: list[str],
) -> None:

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
            writer.writerow(
                row
            )


def median_pairwise_slope(
    x: np.ndarray,
    y: np.ndarray,
) -> float:

    slopes = []

    for i in range(
        len(x)
    ):
        for j in range(
            i + 1,
            len(x),
        ):

            dx = (
                x[j]
                - x[i]
            )

            if dx == 0:
                continue

            slopes.append(
                (
                    y[j]
                    - y[i]
                )
                / dx
            )

    if not slopes:
        raise ValueError(
            "no pairwise slopes"
        )

    return float(
        statistics.median(
            slopes
        )
    )


def predict(
    model: str,
    observations: list[tuple[date, float]],
    origin_date: date,
    origin_price: float,
    horizon: int,
) -> float:

    usable = [
        item
        for item in observations
        if item[0] <= origin_date
    ]

    if model == "LAST_VALUE":

        if len(usable) < 1:
            raise ValueError(
                "insufficient history"
            )

        return float(
            origin_price
        )

    if model in (
        "DRIFT",
        "LOG_DRIFT",
    ):

        if len(usable) < 2:
            raise ValueError(
                "insufficient history"
            )

        first = usable[0][0]

        x = np.asarray(
            [
                (
                    obs_date
                    - first
                ).days
                for obs_date, _
                in usable
            ],
            dtype=float,
        )

        prices = np.asarray(
            [
                price
                for _, price
                in usable
            ],
            dtype=float,
        )

        future_x = float(
            (
                origin_date
                - first
            ).days
            + horizon
        )

        if model == "DRIFT":

            slope, intercept = np.polyfit(
                x,
                prices,
                1,
            )

            value = float(
                slope
                * future_x
                + intercept
            )

            if (
                not np.isfinite(
                    value
                )
                or value <= 0
            ):
                raise ValueError(
                    "invalid drift prediction"
                )

            return value

        slope, intercept = np.polyfit(
            x,
            np.log(
                prices
            ),
            1,
        )

        value = math.exp(
            float(
                slope
                * future_x
                + intercept
            )
        )

        if (
            not np.isfinite(
                value
            )
            or value <= 0
        ):
            raise ValueError(
                "invalid log-drift prediction"
            )

        return float(
            value
        )

    if model == "ROBUST_TREND":

        if len(usable) < 3:
            raise ValueError(
                "insufficient history"
            )

        first = usable[0][0]

        x = np.asarray(
            [
                (
                    obs_date
                    - first
                ).days
                for obs_date, _
                in usable
            ],
            dtype=float,
        )

        y = np.log(
            np.asarray(
                [
                    price
                    for _, price
                    in usable
                ],
                dtype=float,
            )
        )

        slope = median_pairwise_slope(
            x,
            y,
        )

        intercept = float(
            np.median(
                y
                - slope
                * x
            )
        )

        future_x = float(
            (
                origin_date
                - first
            ).days
            + horizon
        )

        value = math.exp(
            intercept
            + slope
            * future_x
        )

        if (
            not np.isfinite(
                value
            )
            or value <= 0
        ):
            raise ValueError(
                "invalid robust prediction"
            )

        return float(
            value
        )

    if model == "EXPONENTIAL_SMOOTHING":

        if len(usable) < 3:
            raise ValueError(
                "insufficient history"
            )

        daily_log_returns = []

        for index in range(
            1,
            len(usable),
        ):

            prior_date, prior_price = (
                usable[
                    index - 1
                ]
            )

            current_date, current_price = (
                usable[
                    index
                ]
            )

            elapsed = (
                current_date
                - prior_date
            ).days

            if elapsed <= 0:
                continue

            daily_log_returns.append(
                math.log(
                    current_price
                    / prior_price
                )
                / float(
                    elapsed
                )
            )

        if len(
            daily_log_returns
        ) < 2:
            raise ValueError(
                "insufficient return intervals"
            )

        alpha = 0.35

        weights = np.asarray(
            [
                (
                    1.0
                    - alpha
                )
                ** (
                    len(
                        daily_log_returns
                    )
                    - 1
                    - index
                )
                for index in range(
                    len(
                        daily_log_returns
                    )
                )
            ],
            dtype=float,
        )

        weights = (
            weights
            / weights.sum()
        )

        daily_drift = float(
            np.dot(
                weights,
                np.asarray(
                    daily_log_returns,
                    dtype=float,
                ),
            )
        )

        value = (
            origin_price
            * math.exp(
                daily_drift
                * float(
                    horizon
                )
            )
        )

        if (
            not np.isfinite(
                value
            )
            or value <= 0
        ):
            raise ValueError(
                "invalid exponential smoothing prediction"
            )

        return float(
            value
        )

    raise ValueError(
        f"unknown model: {model}"
    )


def errors(
    origin_price: float,
    actual_price: float,
    predicted_price: float,
) -> dict[str, float]:

    error = (
        predicted_price
        - actual_price
    )

    absolute_error = abs(
        error
    )

    ape = (
        absolute_error
        / actual_price
    )

    denominator = (
        abs(
            predicted_price
        )
        + abs(
            actual_price
        )
    )

    smape = (
        0.0
        if denominator == 0
        else (
            2.0
            * absolute_error
            / denominator
        )
    )

    actual_return = (
        actual_price
        / origin_price
    ) - 1.0

    predicted_return = (
        predicted_price
        / origin_price
    ) - 1.0

    direction_correct = float(
        np.sign(
            actual_return
        )
        == np.sign(
            predicted_return
        )
    )

    downside_error = max(
        predicted_return
        - actual_return,
        0.0,
    )

    return {
        "error":
            float(error),

        "absolute_error":
            float(
                absolute_error
            ),

        "squared_error":
            float(
                error
                * error
            ),

        "ape":
            float(
                ape
            ),

        "smape":
            float(
                smape
            ),

        "actual_return":
            float(
                actual_return
            ),

        "predicted_return":
            float(
                predicted_return
            ),

        "direction_correct":
            float(
                direction_correct
            ),

        "downside_error":
            float(
                downside_error
            ),
    }


def safe_rank(
    rows: list[dict[str, object]],
) -> float | None:

    if len(rows) < 2:
        return None

    predicted = [
        float(
            row[
                "predicted_return"
            ]
        )
        for row in rows
    ]

    actual = [
        float(
            row[
                "actual_return"
            ]
        )
        for row in rows
    ]

    if (
        len(
            set(
                predicted
            )
        )
        < 2
        or len(
            set(
                actual
            )
        )
        < 2
    ):
        return None

    result = spearmanr(
        predicted,
        actual,
    )

    value = float(
        result.statistic
    )

    if not np.isfinite(
        value
    ):
        return None

    return value


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--canonical-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--history-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--fold-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--matrix-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--runner-sha256",
        required=True,
    )

    parser.add_argument(
        "--contract-sha256",
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    canonical_rows = read_zip_csv(
        args.canonical_package,
        "precollector_canonical_universe_v2.csv",
    )

    history_rows = read_zip_csv(
        args.history_package,
        "precollector_historical_price_authority_v3.csv",
    )

    fold_rows = read_zip_csv(
        args.fold_package,
        "precollector_temporal_fold_ledger_v1.csv",
    )

    matrix_rows = read_zip_csv(
        args.matrix_package,
        "precollector_executable_tournament_matrix_v1.csv",
    )

    if len(
        canonical_rows
    ) != 131:
        fail(
            "canonical universe != 131"
        )

    if len(
        history_rows
    ) != 3390:
        fail(
            "history rows != 3390"
        )

    if len(
        fold_rows
    ) != 7803:
        fail(
            "fold rows != 7803"
        )

    history = defaultdict(
        list
    )

    for row in history_rows:

        history[
            clean(
                row[
                    "canonical_product_id"
                ]
            )
        ].append(
            (
                parse_date(
                    row[
                        "observation_date"
                    ]
                ),
                float(
                    row[
                        "historical_price"
                    ]
                ),
            )
        )

    for canonical_id in history:

        history[
            canonical_id
        ].sort(
            key=lambda item: item[0]
        )

    folds = []

    for row in fold_rows:

        horizon = int(
            row[
                "requested_horizon_days"
            ]
        )

        if horizon not in HORIZONS:
            fail(
                "unexpected horizon"
            )

        folds.append(
            {
                "fold_id":
                    clean(
                        row[
                            "fold_id"
                        ]
                    ),

                "canonical_product_id":
                    clean(
                        row[
                            "canonical_product_id"
                        ]
                    ),

                "product_name":
                    clean(
                        row[
                            "product_name"
                        ]
                    ),

                "horizon":
                    horizon,

                "origin_date":
                    parse_date(
                        row[
                            "origin_date"
                        ]
                    ),

                "origin_price":
                    float(
                        row[
                            "origin_price"
                        ]
                    ),

                "endpoint_date":
                    parse_date(
                        row[
                            "realized_endpoint_date"
                        ]
                    ),

                "endpoint_price":
                    float(
                        row[
                            "realized_endpoint_price"
                        ]
                    ),
            }
        )

    cell_rows = []

    for row in matrix_rows:

        if (
            clean(
                row[
                    "direct_oos_authorized"
                ]
            ).lower()
            != "true"
        ):
            continue

        model = clean(
            row[
                "model_family"
            ]
        )

        if model not in MODELS:
            continue

        cell_rows.append(
            {
                "combination_id":
                    clean(
                        row[
                            "combination_id"
                        ]
                    ),

                "model_family":
                    model,

                "feature_variant":
                    clean(
                        row[
                            "feature_variant"
                        ]
                    ),

                "target_transformation":
                    clean(
                        row[
                            "target_transformation"
                        ]
                    ),

                "requested_horizon_days":
                    int(
                        row[
                            "requested_horizon_days"
                        ]
                    ),
            }
        )

    if len(
        cell_rows
    ) != 180:
        fail(
            f"expected 180 baseline matrix cells, got {len(cell_rows)}"
        )

    semantic_predictions = []
    skipped = []

    total_work = (
        len(folds)
        * len(MODELS)
    )

    completed_work = 0

    for model in MODELS:

        model_predictions = 0
        model_skips = 0

        print(
            f"START_MODEL={model}",
            flush=True,
        )

        for fold in folds:

            completed_work += 1

            canonical_id = (
                fold[
                    "canonical_product_id"
                ]
            )

            try:

                predicted_price = predict(
                    model,
                    history.get(
                        canonical_id,
                        [],
                    ),
                    fold[
                        "origin_date"
                    ],
                    fold[
                        "origin_price"
                    ],
                    fold[
                        "horizon"
                    ],
                )

                row_errors = errors(
                    fold[
                        "origin_price"
                    ],
                    fold[
                        "endpoint_price"
                    ],
                    predicted_price,
                )

                semantic_predictions.append(
                    {
                        "semantic_prediction_id":
                            (
                                f"{model}|"
                                f"H{fold['horizon']}|"
                                f"{fold['fold_id']}"
                            ),

                        "semantic_model_key":
                            (
                                f"{model}|"
                                f"H{fold['horizon']}"
                            ),

                        "model_family":
                            model,

                        "requested_horizon_days":
                            fold[
                                "horizon"
                            ],

                        "fold_id":
                            fold[
                                "fold_id"
                            ],

                        "canonical_product_id":
                            canonical_id,

                        "product_name":
                            fold[
                                "product_name"
                            ],

                        "origin_date":
                            fold[
                                "origin_date"
                            ].isoformat(),

                        "origin_price":
                            fold[
                                "origin_price"
                            ],

                        "realized_endpoint_date":
                            fold[
                                "endpoint_date"
                            ].isoformat(),

                        "actual_endpoint_price":
                            fold[
                                "endpoint_price"
                            ],

                        "predicted_endpoint_price":
                            predicted_price,

                        **row_errors,
                    }
                )

                model_predictions += 1

            except Exception as exc:

                skipped.append(
                    {
                        "model_family":
                            model,

                        "requested_horizon_days":
                            fold[
                                "horizon"
                            ],

                        "fold_id":
                            fold[
                                "fold_id"
                            ],

                        "canonical_product_id":
                            canonical_id,

                        "origin_date":
                            fold[
                                "origin_date"
                            ].isoformat(),

                        "skip_reason":
                            str(
                                exc
                            ),
                    }
                )

                model_skips += 1

        print(
            (
                f"COMPLETE_MODEL={model}"
                f"|PREDICTIONS={model_predictions}"
                f"|SKIPS={model_skips}"
                f"|PROGRESS={completed_work}/{total_work}"
            ),
            flush=True,
        )

    if not semantic_predictions:
        fail(
            "no baseline predictions generated"
        )

    # ========================================================================
    # Semantic scorecard
    # ========================================================================

    semantic_groups = defaultdict(
        list
    )

    for row in semantic_predictions:

        semantic_groups[
            (
                row[
                    "model_family"
                ],
                int(
                    row[
                        "requested_horizon_days"
                    ]
                ),
            )
        ].append(
            row
        )

    semantic_scorecard = []

    for (
        model,
        horizon,
    ), rows in sorted(
        semantic_groups.items()
    ):

        by_origin = defaultdict(
            list
        )

        for row in rows:
            by_origin[
                row[
                    "origin_date"
                ]
            ].append(
                row
            )

        ranks = []

        for origin_rows in by_origin.values():

            rank = safe_rank(
                origin_rows
            )

            if rank is not None:
                ranks.append(
                    rank
                )

        semantic_scorecard.append(
            {
                "semantic_model_key":
                    f"{model}|H{horizon}",

                "model_family":
                    model,

                "requested_horizon_days":
                    horizon,

                "prediction_rows":
                    len(rows),

                "product_count":
                    len(
                        {
                            row[
                                "canonical_product_id"
                            ]
                            for row in rows
                        }
                    ),

                "origin_count":
                    len(
                        by_origin
                    ),

                "SMAPE":
                    float(
                        np.mean(
                            [
                                row[
                                    "smape"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "MAE":
                    float(
                        np.mean(
                            [
                                row[
                                    "absolute_error"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "RMSE":
                    float(
                        math.sqrt(
                            np.mean(
                                [
                                    row[
                                        "squared_error"
                                    ]
                                    for row in rows
                                ]
                            )
                        )
                    ),

                "MEDIAN_APE":
                    float(
                        np.median(
                            [
                                row[
                                    "ape"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "BIAS":
                    float(
                        np.mean(
                            [
                                row[
                                    "error"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "DIRECTIONAL_ACCURACY":
                    float(
                        np.mean(
                            [
                                row[
                                    "direction_correct"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "DOWNSIDE_ERROR":
                    float(
                        np.mean(
                            [
                                row[
                                    "downside_error"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "RANK_CORRELATION":
                    (
                        ""
                        if not ranks
                        else float(
                            np.mean(
                                ranks
                            )
                        )
                    ),
            }
        )

    if len(
        semantic_scorecard
    ) != 15:
        fail(
            f"expected 15 semantic scorecard rows, got {len(semantic_scorecard)}"
        )

    semantic_lookup = {
        (
            row[
                "model_family"
            ],
            int(
                row[
                    "requested_horizon_days"
                ]
            ),
        ): row
        for row in semantic_scorecard
    }

    # ========================================================================
    # 180 governed matrix cells mapped to 15 semantic predictors
    # ========================================================================

    cell_scorecard = []

    for cell in cell_rows:

        semantic = semantic_lookup[
            (
                cell[
                    "model_family"
                ],
                cell[
                    "requested_horizon_days"
                ],
            )
        ]

        cell_scorecard.append(
            {
                **cell,

                "semantic_model_key":
                    semantic[
                        "semantic_model_key"
                    ],

                "prediction_rows":
                    semantic[
                        "prediction_rows"
                    ],

                "SMAPE":
                    semantic[
                        "SMAPE"
                    ],

                "MAE":
                    semantic[
                        "MAE"
                    ],

                "RMSE":
                    semantic[
                        "RMSE"
                    ],

                "MEDIAN_APE":
                    semantic[
                        "MEDIAN_APE"
                    ],

                "BIAS":
                    semantic[
                        "BIAS"
                    ],

                "DIRECTIONAL_ACCURACY":
                    semantic[
                        "DIRECTIONAL_ACCURACY"
                    ],

                "DOWNSIDE_ERROR":
                    semantic[
                        "DOWNSIDE_ERROR"
                    ],

                "RANK_CORRELATION":
                    semantic[
                        "RANK_CORRELATION"
                    ],

                "semantic_duplicate":
                    "true",
            }
        )

    if len(
        cell_scorecard
    ) != 180:
        fail(
            "governed baseline cell scorecard != 180"
        )

    # ========================================================================
    # Product error ledger
    # ========================================================================

    product_groups = defaultdict(
        list
    )

    for row in semantic_predictions:

        product_groups[
            (
                row[
                    "model_family"
                ],
                row[
                    "requested_horizon_days"
                ],
                row[
                    "canonical_product_id"
                ],
                row[
                    "product_name"
                ],
            )
        ].append(
            row
        )

    product_rows = []

    for key, rows in sorted(
        product_groups.items()
    ):

        (
            model,
            horizon,
            canonical_id,
            product_name,
        ) = key

        product_rows.append(
            {
                "model_family":
                    model,

                "requested_horizon_days":
                    horizon,

                "canonical_product_id":
                    canonical_id,

                "product_name":
                    product_name,

                "prediction_rows":
                    len(rows),

                "SMAPE":
                    float(
                        np.mean(
                            [
                                row[
                                    "smape"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "MAE":
                    float(
                        np.mean(
                            [
                                row[
                                    "absolute_error"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "BIAS":
                    float(
                        np.mean(
                            [
                                row[
                                    "error"
                                ]
                                for row in rows
                            ]
                        )
                    ),
            }
        )

    # ========================================================================
    # Descriptive lowest baseline SMAPE by horizon
    # ========================================================================

    descriptive = {}

    for horizon in HORIZONS:

        candidates = [
            row
            for row in semantic_scorecard
            if (
                row[
                    "requested_horizon_days"
                ]
                == horizon
            )
        ]

        best = min(
            candidates,
            key=lambda row: float(
                row[
                    "SMAPE"
                ]
            ),
        )

        descriptive[
            str(
                horizon
            )
        ] = {
            "model_family":
                best[
                    "model_family"
                ],

            "SMAPE":
                best[
                    "SMAPE"
                ],

            "status":
                "DESCRIPTIVE_BASELINE_ONLY_NOT_CERTIFIED_WINNER",
        }

    # ========================================================================
    # Write outputs
    # ========================================================================

    root = args.output_root.resolve()

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    prediction_path = (
        root
        / "precollector_15wa_semantic_prediction_ledger_v1.csv"
    )

    semantic_scorecard_path = (
        root
        / "precollector_15wa_semantic_scorecard_v1.csv"
    )

    cell_scorecard_path = (
        root
        / "precollector_15wa_governed_cell_scorecard_v1.csv"
    )

    product_path = (
        root
        / "precollector_15wa_product_oos_error_ledger_v1.csv"
    )

    skipped_path = (
        root
        / "precollector_15wa_skipped_fold_ledger_v1.csv"
    )

    summary_path = (
        root
        / "precollector_15wa_summary_v1.json"
    )

    manifest_path = (
        root
        / "precollector_15wa_manifest_v1.json"
    )

    write_csv(
        prediction_path,
        semantic_predictions,
        [
            "semantic_prediction_id",
            "semantic_model_key",
            "model_family",
            "requested_horizon_days",
            "fold_id",
            "canonical_product_id",
            "product_name",
            "origin_date",
            "origin_price",
            "realized_endpoint_date",
            "actual_endpoint_price",
            "predicted_endpoint_price",
            "error",
            "absolute_error",
            "squared_error",
            "ape",
            "smape",
            "actual_return",
            "predicted_return",
            "direction_correct",
            "downside_error",
        ],
    )

    write_csv(
        semantic_scorecard_path,
        semantic_scorecard,
        [
            "semantic_model_key",
            "model_family",
            "requested_horizon_days",
            "prediction_rows",
            "product_count",
            "origin_count",
            "SMAPE",
            "MAE",
            "RMSE",
            "MEDIAN_APE",
            "BIAS",
            "DIRECTIONAL_ACCURACY",
            "DOWNSIDE_ERROR",
            "RANK_CORRELATION",
        ],
    )

    write_csv(
        cell_scorecard_path,
        cell_scorecard,
        [
            "combination_id",
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "semantic_model_key",
            "prediction_rows",
            "SMAPE",
            "MAE",
            "RMSE",
            "MEDIAN_APE",
            "BIAS",
            "DIRECTIONAL_ACCURACY",
            "DOWNSIDE_ERROR",
            "RANK_CORRELATION",
            "semantic_duplicate",
        ],
    )

    write_csv(
        product_path,
        product_rows,
        [
            "model_family",
            "requested_horizon_days",
            "canonical_product_id",
            "product_name",
            "prediction_rows",
            "SMAPE",
            "MAE",
            "BIAS",
        ],
    )

    write_csv(
        skipped_path,
        skipped,
        [
            "model_family",
            "requested_horizon_days",
            "fold_id",
            "canonical_product_id",
            "origin_date",
            "skip_reason",
        ],
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_A",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "batch_id":
            "15W-A",

        "models_executed":
            list(
                MODELS
            ),

        "model_count":
            5,

        "temporal_fold_rows":
            len(
                folds
            ),

        "semantic_model_horizon_rows":
            len(
                semantic_scorecard
            ),

        "governed_matrix_cells":
            len(
                cell_scorecard
            ),

        "semantic_prediction_rows":
            len(
                semantic_predictions
            ),

        "skipped_rows":
            len(
                skipped
            ),

        "descriptive_lowest_smape":
            descriptive,

        "certified_winner_selected":
            False,

        "product_holdout_executed":
            False,

        "product_exclusions_assigned":
            0,

        "production_model_selection_authorized":
            False,

        "monte_carlo_execution_authorized":
            False,

        "forecast_execution_authorized":
            False,

        "ranking_execution_authorized":
            False,

        "authorized_next_stage":
            "RUN_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_B",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    members = [
        prediction_path,
        semantic_scorecard_path,
        cell_scorecard_path,
        product_path,
        skipped_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_15wa_manifest_v1",

        "runner_sha256_pre_execution":
            args.runner_sha256,

        "contract_sha256_pre_execution":
            args.contract_sha256,

        "members": [
            {
                "file_name":
                    path.name,

                "sha256":
                    sha256_file(
                        path
                    ),

                "byte_length":
                    path.stat().st_size,
            }
            for path in members
        ],
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "PASS_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_A"
    )

    print(
        "MODELS_EXECUTED=5"
    )

    print(
        f"SEMANTIC_PREDICTION_ROWS={len(semantic_predictions)}"
    )

    print(
        f"SKIPPED_ROWS={len(skipped)}"
    )

    print(
        "SEMANTIC_MODEL_HORIZON_ROWS=15"
    )

    print(
        "GOVERNED_MATRIX_CELLS=180"
    )

    for horizon in HORIZONS:

        best = descriptive[
            str(
                horizon
            )
        ]

        print(
            (
                f"HORIZON_{horizon}_LOWEST_BASELINE_SMAPE="
                f"{best['model_family']}|"
                f"{best['SMAPE']:.8f}"
            )
        )

    print(
        "CERTIFIED_WINNER_SELECTED=FALSE"
    )

    print(
        "PRODUCT_HOLDOUT_EXECUTED=FALSE"
    )

    print(
        "PRODUCT_EXCLUSIONS_ASSIGNED=0"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )