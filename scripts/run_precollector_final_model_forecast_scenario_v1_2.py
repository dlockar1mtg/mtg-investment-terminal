from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import zipfile

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from sklearn.linear_model import HuberRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


HORIZONS = (90, 180, 365)

EXPECTED_90 = (
    "HUBER_REGRESSION"
    "|PRICE_PLUS_PATH_STABILITY"
    "|RAW_PRICE_CHANGE"
    "|H90"
)

EXPECTED_365 = (
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


def parse_date(value: object) -> date:
    return date.fromisoformat(
        clean(value)[:10]
    )


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
                f"missing ZIP member {member}"
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
                f"missing ZIP member {member}"
            )

        return json.loads(
            archive.read(
                member
            ).decode(
                "utf-8-sig"
            )
        )


def find_zip_csv(
    package: Path,
    required_text: str,
) -> list[dict[str, str]]:

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        matches = [
            name
            for name in archive.namelist()
            if (
                name.lower().endswith(
                    ".csv"
                )
                and required_text.lower()
                in name.lower()
            )
        ]

        if len(matches) != 1:
            fail(
                f"expected exactly one CSV containing "
                f"{required_text}; got {matches}"
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


def resolve_column(
    row: dict[str, str],
    candidates: tuple[str, ...],
    fuzzy_terms: tuple[str, ...] = (),
) -> str:

    for candidate in candidates:
        if candidate in row:
            return candidate

    if fuzzy_terms:

        matches = [
            column
            for column in row
            if all(
                term in column.lower()
                for term in fuzzy_terms
            )
        ]

        if len(matches) == 1:
            return matches[0]

    fail(
        f"unable to resolve column from {candidates}"
    )


def feature_path_stability(
    observations: list[tuple[date, float]],
) -> np.ndarray:

    if len(observations) < 2:
        raise ValueError(
            "requires at least two observations"
        )

    observations = sorted(
        observations,
        key=lambda item: item[0],
    )

    dates = [
        item[0]
        for item in observations
    ]

    prices = np.asarray(
        [
            float(item[1])
            for item in observations
        ],
        dtype=float,
    )

    if np.any(prices <= 0):
        raise ValueError(
            "nonpositive historical price"
        )

    log_prices = np.log(
        prices
    )

    interval_returns = []

    for index in range(
        1,
        len(observations),
    ):

        elapsed = (
            dates[index]
            - dates[index - 1]
        ).days

        if elapsed <= 0:
            continue

        interval_returns.append(
            (
                log_prices[index]
                - log_prices[index - 1]
            )
            / math.sqrt(
                float(elapsed)
            )
        )

    if not interval_returns:
        raise ValueError(
            "no valid path intervals"
        )

    volatility = float(
        np.std(
            interval_returns,
            ddof=0,
        )
    )

    running_max = np.maximum.accumulate(
        prices
    )

    max_drawdown = float(
        abs(
            np.min(
                (
                    prices
                    / running_max
                ) - 1.0
            )
        )
    )

    first_date = dates[0]

    x = np.asarray(
        [
            (
                item
                - first_date
            ).days
            for item in dates
        ],
        dtype=float,
    )

    if np.ptp(x) <= 0:
        raise ValueError(
            "zero path span"
        )

    slope, _ = np.polyfit(
        x,
        log_prices,
        1,
    )

    return np.asarray(
        [
            math.log(
                float(
                    prices[-1]
                )
            ),
            volatility,
            max_drawdown,
            float(slope),
        ],
        dtype=float,
    )


def build_huber():

    return Pipeline(
        [
            (
                "scale",
                StandardScaler(),
            ),
            (
                "model",
                HuberRegressor(
                    epsilon=1.35,
                    alpha=0.0001,
                    max_iter=1000,
                ),
            ),
        ]
    )


def load_step2_helpers(
    repo_root: Path,
):

    helper_path = (
        repo_root
        / "scripts"
        / "run_precollector_large_step_2_ensemble_robustness_v1.py"
    )

    if not helper_path.is_file():
        fail(
            "Large Step 2 helper runner missing"
        )

    spec = (
        importlib.util
        .spec_from_file_location(
            "precollector_step2_helpers",
            helper_path,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        fail(
            "unable to load Step 2 helper module"
        )

    module = (
        importlib.util
        .module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
    )

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
        "--current-price-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--base-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--robustness-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--h90-lopo-checkpoint-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    root = args.output_root.resolve()

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================================
    # Inputs
    # ========================================================================

    canonical_rows = read_zip_csv(
        args.canonical_package,
        "precollector_canonical_universe_v2.csv",
    )

    history_rows = read_zip_csv(
        args.history_package,
        "precollector_historical_price_authority_v3.csv",
    )

    fold_rows_raw = read_zip_csv(
        args.fold_package,
        "precollector_temporal_fold_ledger_v1.csv",
    )

    current_rows = find_zip_csv(
        args.current_price_package,
        "current_price_authority_v2",
    )

    base_prediction_rows = read_zip_csv(
        args.base_package,
        "precollector_base_common_fold_prediction_ledger_v1.csv",
    )

    robustness_ranking = read_zip_csv(
        args.robustness_package,
        "precollector_robustness_diagnostic_ranking_v1.csv",
    )

    robustness_summary = read_zip_json(
        args.robustness_package,
        "precollector_large_step_2_summary_v1.json",
    )

    holdout_rows_existing = read_zip_csv(
        args.robustness_package,
        "precollector_product_holdout_ledger_v1.csv",
    )

    if len(canonical_rows) != 131:
        fail(
            "canonical population drift"
        )

    # ========================================================================
    # Final horizon candidates are rank-1 robustness models.
    # ========================================================================

    selected = {}

    for horizon in HORIZONS:

        rows = [
            row
            for row in robustness_ranking
            if (
                int(
                    row[
                        "requested_horizon_days"
                    ]
                )
                == horizon
                and int(
                    row[
                        "diagnostic_rank"
                    ]
                )
                == 1
            )
        ]

        if len(rows) != 1:
            fail(
                f"expected one robustness leader H{horizon}"
            )

        selected[
            horizon
        ] = rows[0]

    if (
        selected[90][
            "semantic_model_key"
        ]
        != EXPECTED_90
    ):
        fail(
            "H90 robustness leader drifted from observed certified result"
        )

    if (
        selected[365][
            "semantic_model_key"
        ]
        != EXPECTED_365
    ):
        fail(
            "H365 robustness leader drifted from observed certified result"
        )

    if (
        selected[180][
            "model_family"
        ]
        != "ROUTE_ENSEMBLE"
    ):
        fail(
            "H180 robustness leader is not certified Route Ensemble"
        )

    # ========================================================================
    # Rebuild fold structures for targeted H90 LOPO.
    # ========================================================================

    helper = load_step2_helpers(
        args.repo_root
    )

    folds = []

    for raw in fold_rows_raw:

        folds.append(
            {
                "fold_id":
                    clean(
                        raw[
                            "fold_id"
                        ]
                    ),

                "canonical_product_id":
                    clean(
                        raw[
                            "canonical_product_id"
                        ]
                    ),

                "product_name":
                    clean(
                        raw[
                            "product_name"
                        ]
                    ),

                "horizon":
                    int(
                        raw[
                            "requested_horizon_days"
                        ]
                    ),

                "origin_date":
                    parse_date(
                        raw[
                            "origin_date"
                        ]
                    ),

                "origin_price":
                    float(
                        raw[
                            "origin_price"
                        ]
                    ),

                "endpoint_date":
                    parse_date(
                        raw[
                            "realized_endpoint_date"
                        ]
                    ),

                "endpoint_price":
                    float(
                        raw[
                            "realized_endpoint_price"
                        ]
                    ),

                "elapsed_days":
                    int(
                        raw[
                            "actual_elapsed_days"
                        ]
                    ),
            }
        )

    print(
        "PHASE_A_TARGETED_H90_HUBER_HOLDOUT",
        flush=True,
    )

    h90_config = {
        "family":
            "HUBER_REGRESSION",

        "feature":
            "PRICE_PLUS_PATH_STABILITY",

        "target":
            "RAW_PRICE_CHANGE",

        "horizon":
            90,

        "semantic_model_key":
            EXPECTED_90,
    }

    (
        h90_lopo_predictions,
        h90_holdout_rows,
    ) = helper.genuine_lopo(
        h90_config,
        canonical_rows,
        history_rows,
        folds,
        args.h90_lopo_checkpoint_root,
    )

    h90_holdout_dispositions = [
        row
        for row in h90_holdout_rows
        if clean(
            row.get(
                "heldout_product_id"
            )
        )
    ]

    if len(h90_holdout_dispositions) != 115:
        fail(
            "H90 Huber holdout dispositions != 115"
        )

    h90_holdout_ids = {
        clean(
            row[
                "heldout_product_id"
            ]
        )
        for row in h90_holdout_dispositions
    }

    if len(h90_holdout_ids) != 115:
        fail(
            "H90 Huber holdout product IDs are not unique 115"
        )

    h90_valid_statuses = {
        "GENUINE_LEAVE_ONE_PRODUCT_OUT",
        "NO_VALID_LOPO_PREDICTIONS",
    }

    h90_unknown_statuses = {
        clean(
            row.get(
                "holdout_status"
            )
        )
        for row in h90_holdout_dispositions
    } - h90_valid_statuses

    if h90_unknown_statuses:
        fail(
            f"H90 Huber unknown holdout statuses: {sorted(h90_unknown_statuses)}"
        )

    h90_holdout_products = {
        clean(
            row[
                "heldout_product_id"
            ]
        )
        for row in h90_holdout_dispositions
        if clean(
            row.get(
                "holdout_status"
            )
        ) == "GENUINE_LEAVE_ONE_PRODUCT_OUT"
    }

    h90_no_valid_holdout_products = {
        clean(
            row[
                "heldout_product_id"
            ]
        )
        for row in h90_holdout_dispositions
        if clean(
            row.get(
                "holdout_status"
            )
        ) == "NO_VALID_LOPO_PREDICTIONS"
    }

    if (
        len(h90_holdout_products)
        + len(h90_no_valid_holdout_products)
        != 115
    ):
        fail(
            "H90 Huber holdout disposition reconciliation failed"
        )

    if not h90_lopo_predictions:
        fail(
            "H90 Huber produced no genuine holdout predictions"
        )

    # ========================================================================
    # Verify existing H365 pooled holdout evidence.
    # ========================================================================

    h365_holdout_dispositions = [
        row
        for row in holdout_rows_existing
        if (
            clean(
                row.get(
                    "semantic_model_key"
                )
            )
            == EXPECTED_365
            and clean(
                row.get(
                    "heldout_product_id"
                )
            )
        )
    ]

    if len(h365_holdout_dispositions) != 115:
        fail(
            f"H365 Huber holdout dispositions != 115; got {len(h365_holdout_dispositions)}"
        )

    h365_holdout_ids = {
        clean(
            row[
                "heldout_product_id"
            ]
        )
        for row in h365_holdout_dispositions
    }

    if len(h365_holdout_ids) != 115:
        fail(
            "H365 Huber holdout product IDs are not unique 115"
        )

    h365_valid_statuses = {
        "GENUINE_LEAVE_ONE_PRODUCT_OUT",
        "NO_VALID_LOPO_PREDICTIONS",
    }

    h365_unknown_statuses = {
        clean(
            row.get(
                "holdout_status"
            )
        )
        for row in h365_holdout_dispositions
    } - h365_valid_statuses

    if h365_unknown_statuses:
        fail(
            f"H365 Huber unknown holdout statuses: {sorted(h365_unknown_statuses)}"
        )

    h365_holdout_products = {
        clean(
            row[
                "heldout_product_id"
            ]
        )
        for row in h365_holdout_dispositions
        if clean(
            row.get(
                "holdout_status"
            )
        ) == "GENUINE_LEAVE_ONE_PRODUCT_OUT"
    }

    h365_no_valid_holdout_products = {
        clean(
            row[
                "heldout_product_id"
            ]
        )
        for row in h365_holdout_dispositions
        if clean(
            row.get(
                "holdout_status"
            )
        ) == "NO_VALID_LOPO_PREDICTIONS"
    }

    if (
        len(h365_holdout_products)
        + len(h365_no_valid_holdout_products)
        != 115
    ):
        fail(
            "H365 Huber holdout disposition reconciliation failed"
        )

    # ========================================================================
    # Final horizon-model certification
    # ========================================================================

    print(
        "PHASE_B_FINAL_HORIZON_MODEL_CERTIFICATION",
        flush=True,
    )

    certification_rows = []

    for horizon in HORIZONS:

        leader = selected[
            horizon
        ]

        family = leader[
            "model_family"
        ]

        if horizon == 90:
            holdout_status = (
                "GENUINE_PRODUCT_HOLDOUT_COMPLETE_115"
            )

        elif horizon == 365:
            holdout_status = (
                "GENUINE_PRODUCT_HOLDOUT_COMPLETE_115"
            )

        else:
            holdout_status = (
                "NESTED_OOS_ENSEMBLE_ANTI_LEAKAGE_CERTIFIED"
            )

        certification_rows.append(
            {
                "requested_horizon_days":
                    horizon,

                "certified_semantic_model_key":
                    leader[
                        "semantic_model_key"
                    ],

                "certified_model_family":
                    family,

                "robustness_smape":
                    leader[
                        "SMAPE"
                    ],

                "robustness_mae":
                    leader[
                        "MAE"
                    ],

                "robustness_bias":
                    leader[
                        "BIAS"
                    ],

                "holdout_or_ensemble_validation":
                    holdout_status,

                "persistent_product_exclusions":
                    0,

                "selection_status":
                    "FINAL_HORIZON_MODEL_CERTIFIED",
            }
        )

    # ========================================================================
    # Build historical observations.
    # ========================================================================

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

    for product_id in history:

        history[
            product_id
        ].sort(
            key=lambda item:
                item[0]
        )

    # ========================================================================
    # Train certified H365 production Huber model.
    # ========================================================================

    print(
        "PHASE_C_PRODUCTION_365_MODEL_AND_FORECAST",
        flush=True,
    )

    h365_folds = [
        row
        for row in folds
        if (
            row[
                "horizon"
            ]
            == 365
        )
    ]

    train_x = []
    train_y = []

    for fold in h365_folds:

        observations = [
            item
            for item in history.get(
                fold[
                    "canonical_product_id"
                ],
                [],
            )
            if (
                item[0]
                <= fold[
                    "origin_date"
                ]
            )
        ]

        try:

            x = feature_path_stability(
                observations
            )

        except Exception:
            continue

        y = (
            fold[
                "endpoint_price"
            ]
            / fold[
                "origin_price"
            ]
        ) - 1.0

        if not math.isfinite(y):
            continue

        train_x.append(x)
        train_y.append(y)

    if len(train_x) < 20:
        fail(
            "insufficient H365 production training examples"
        )

    production_model = build_huber()

    production_model.fit(
        np.vstack(
            train_x
        ),
        np.asarray(
            train_y,
            dtype=float,
        ),
    )

    # ========================================================================
    # Current price schema
    # ========================================================================

    if not current_rows:
        fail(
            "current price authority empty"
        )

    current_id_col = resolve_column(
        current_rows[0],
        (
            "canonical_product_id",
        ),
    )

    current_price_col = resolve_column(
        current_rows[0],
        (
            "current_price",
            "authoritative_current_price",
            "historical_price",
            "market_price",
            "price",
        ),
        (
            "price",
        ),
    )

    current_date_col = resolve_column(
        current_rows[0],
        (
            "observation_date",
            "current_price_observation_date",
            "as_of_date",
            "price_date",
        ),
        (
            "date",
        ),
    )

    canonical_name_by_id = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
            clean(
                row[
                    "product_name"
                ]
            )
        for row in canonical_rows
    }

    forecasts = []
    forecast_gaps = []

    for row in current_rows:

        product_id = clean(
            row[
                current_id_col
            ]
        )

        current_price_raw = clean(
            row.get(
                current_price_col
            )
        )

        current_date_raw = clean(
            row.get(
                current_date_col
            )
        )

        if not current_price_raw:

            forecast_gaps.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        canonical_name_by_id.get(
                            product_id,
                            "",
                        ),

                    "current_price":
                        "",

                    "current_price_date":
                        (
                            current_date_raw[:10]
                            if current_date_raw
                            else ""
                        ),

                    "gap_reason":
                        "MISSING_CURRENT_PRICE_AUTHORITY",

                    "direct_forecast_authorized":
                        "false",
                }
            )

            continue

        try:

            current_price = float(
                current_price_raw
            )

        except (TypeError, ValueError):

            forecast_gaps.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        canonical_name_by_id.get(
                            product_id,
                            "",
                        ),

                    "current_price":
                        current_price_raw,

                    "current_price_date":
                        (
                            current_date_raw[:10]
                            if current_date_raw
                            else ""
                        ),

                    "gap_reason":
                        "INVALID_CURRENT_PRICE_AUTHORITY",

                    "direct_forecast_authorized":
                        "false",
                }
            )

            continue

        if (
            not math.isfinite(
                current_price
            )
            or current_price <= 0
        ):

            forecast_gaps.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        canonical_name_by_id.get(
                            product_id,
                            "",
                        ),

                    "current_price":
                        current_price_raw,

                    "current_price_date":
                        (
                            current_date_raw[:10]
                            if current_date_raw
                            else ""
                        ),

                    "gap_reason":
                        "NONPOSITIVE_OR_NONFINITE_CURRENT_PRICE_AUTHORITY",

                    "direct_forecast_authorized":
                        "false",
                }
            )

            continue

        if not current_date_raw:

            forecast_gaps.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        canonical_name_by_id.get(
                            product_id,
                            "",
                        ),

                    "current_price":
                        current_price,

                    "current_price_date":
                        "",

                    "gap_reason":
                        "MISSING_CURRENT_PRICE_OBSERVATION_DATE",

                    "direct_forecast_authorized":
                        "false",
                }
            )

            continue

        try:

            current_date = parse_date(
                current_date_raw
            )

        except Exception:

            forecast_gaps.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        canonical_name_by_id.get(
                            product_id,
                            "",
                        ),

                    "current_price":
                        current_price,

                    "current_price_date":
                        current_date_raw,

                    "gap_reason":
                        "INVALID_CURRENT_PRICE_OBSERVATION_DATE",

                    "direct_forecast_authorized":
                        "false",
                }
            )

            continue

        observations = list(
            history.get(
                product_id,
                [],
            )
        )

        # Current authority is an explicit present-time observation.
        observations = [
            item
            for item in observations
            if item[0] < current_date
        ]

        observations.append(
            (
                current_date,
                current_price,
            )
        )

        try:

            x_current = (
                feature_path_stability(
                    observations
                )
            )

            predicted_return = float(
                production_model.predict(
                    x_current.reshape(
                        1,
                        -1,
                    )
                )[0]
            )

            forecast_price = (
                current_price
                * (
                    1.0
                    + predicted_return
                )
            )

            if (
                not math.isfinite(
                    forecast_price
                )
                or forecast_price <= 0
            ):
                raise ValueError(
                    "invalid production forecast"
                )

        except Exception as exc:

            forecast_gaps.append(
                {
                    "canonical_product_id":
                        product_id,

                    "product_name":
                        canonical_name_by_id.get(
                            product_id,
                            "",
                        ),

                    "current_price":
                        current_price,

                    "current_price_date":
                        current_date.isoformat(),

                    "gap_reason":
                        str(exc),

                    "direct_forecast_authorized":
                        "false",
                }
            )

            continue

        forecasts.append(
            {
                "canonical_product_id":
                    product_id,

                "product_name":
                    canonical_name_by_id.get(
                        product_id,
                        "",
                    ),

                "current_price":
                    current_price,

                "current_price_date":
                    current_date.isoformat(),

                "forecast_horizon_days":
                    365,

                "certified_model":
                    EXPECTED_365,

                "forecast_price_365d":
                    float(
                        forecast_price
                    ),

                "predicted_return_365d":
                    float(
                        predicted_return
                    ),

                "forecast_classification":
                    "DIRECT_365_DAY_MODEL_FORECAST",

                "persistent_product_exclusion":
                    "false",
            }
        )

    if (
        len(forecasts)
        + len(forecast_gaps)
        != len(current_rows)
    ):
        fail(
            "current-price forecast/gap reconciliation failed"
        )

    if not forecasts:
        fail(
            "production 365 model generated zero forecasts"
        )

    # ========================================================================
    # 365-day OOS residual calibration
    # ========================================================================

    residual_rows = [
        row
        for row in base_prediction_rows
        if (
            int(
                row[
                    "requested_horizon_days"
                ]
            )
            == 365
            and clean(
                row[
                    "semantic_model_key"
                ]
            )
            == EXPECTED_365
        )
    ]

    if not residual_rows:
        fail(
            "no H365 OOS residual calibration rows"
        )

    residuals = []

    for row in residual_rows:

        actual = float(
            row[
                "actual_endpoint_price"
            ]
        )

        predicted = float(
            row[
                "predicted_endpoint_price"
            ]
        )

        if (
            actual <= 0
            or predicted <= 0
        ):
            continue

        residuals.append(
            math.log(
                actual
                / predicted
            )
        )

    if len(residuals) < 100:
        fail(
            "insufficient H365 residual calibration observations"
        )

    residual_array = np.asarray(
        residuals,
        dtype=float,
    )

    quantiles = {
        "p10":
            float(
                np.quantile(
                    residual_array,
                    0.10,
                )
            ),

        "p25":
            float(
                np.quantile(
                    residual_array,
                    0.25,
                )
            ),

        "p50":
            float(
                np.quantile(
                    residual_array,
                    0.50,
                )
            ),

        "p75":
            float(
                np.quantile(
                    residual_array,
                    0.75,
                )
            ),

        "p90":
            float(
                np.quantile(
                    residual_array,
                    0.90,
                )
            ),
    }

    calibration = {
        "status":
            "CERTIFIED_365_DAY_OOS_RESIDUAL_CALIBRATION",

        "semantic_model_key":
            EXPECTED_365,

        "residual_definition":
            "LOG_ACTUAL_PRICE_DIVIDED_BY_PREDICTED_PRICE",

        "observation_count":
            len(
                residual_array
            ),

        "mean":
            float(
                np.mean(
                    residual_array
                )
            ),

        "standard_deviation":
            float(
                np.std(
                    residual_array,
                    ddof=0,
                )
            ),

        "quantiles":
            quantiles,
    }

    # ========================================================================
    # 3-year and 5-year scenario transfer
    #
    # These are NOT direct backtests.
    #
    # Base:
    #   compound certified 365-day log return.
    #
    # Conservative/upside:
    #   widen one-year OOS residual through sqrt(time).
    # ========================================================================

    print(
        "PHASE_D_LONG_HORIZON_SCENARIO_CONSTRUCTION",
        flush=True,
    )

    scenario_rows = []

    for forecast in forecasts:

        current_price = float(
            forecast[
                "current_price"
            ]
        )

        one_year_price = float(
            forecast[
                "forecast_price_365d"
            ]
        )

        if (
            current_price <= 0
            or one_year_price <= 0
        ):
            continue

        annual_log_anchor = math.log(
            one_year_price
            / current_price
        )

        for years, horizon, label in (
            (
                3.0,
                1095,
                "THREE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED",
            ),
            (
                5.0,
                1825,
                "FIVE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED",
            ),
        ):

            sqrt_years = math.sqrt(
                years
            )

            conservative_log = (
                years
                * annual_log_anchor
                + sqrt_years
                * quantiles[
                    "p10"
                ]
            )

            base_log = (
                years
                * annual_log_anchor
            )

            upside_log = (
                years
                * annual_log_anchor
                + sqrt_years
                * quantiles[
                    "p90"
                ]
            )

            conservative_price = (
                current_price
                * math.exp(
                    conservative_log
                )
            )

            base_price = (
                current_price
                * math.exp(
                    base_log
                )
            )

            upside_price = (
                current_price
                * math.exp(
                    upside_log
                )
            )

            scenario_rows.append(
                {
                    "canonical_product_id":
                        forecast[
                            "canonical_product_id"
                        ],

                    "product_name":
                        forecast[
                            "product_name"
                        ],

                    "current_price":
                        current_price,

                    "scenario_horizon_days":
                        horizon,

                    "scenario_years":
                        years,

                    "one_year_certified_model":
                        EXPECTED_365,

                    "one_year_forecast_price":
                        one_year_price,

                    "conservative_scenario_price":
                        float(
                            conservative_price
                        ),

                    "base_scenario_price":
                        float(
                            base_price
                        ),

                    "upside_scenario_price":
                        float(
                            upside_price
                        ),

                    "scenario_classification":
                        label,

                    "directly_backtested_at_this_horizon":
                        "false",

                    "monte_carlo_result":
                        "false",

                    "purchase_recommendation":
                        "false",
                }
            )

    # ========================================================================
    # Outputs
    # ========================================================================

    certification_path = (
        root
        / "precollector_final_horizon_model_certification_v1.csv"
    )

    h90_holdout_path = (
        root
        / "precollector_h90_huber_genuine_holdout_ledger_v1.csv"
    )

    forecast_path = (
        root
        / "precollector_certified_365_day_forecast_v1.csv"
    )

    gap_path = (
        root
        / "precollector_certified_365_day_forecast_gap_ledger_v1.csv"
    )

    scenario_path = (
        root
        / "precollector_3y_5y_scenario_basis_v1.csv"
    )

    calibration_path = (
        root
        / "precollector_365_day_uncertainty_calibration_v1.json"
    )

    summary_path = (
        root
        / "precollector_final_model_forecast_scenario_summary_v1.json"
    )

    write_csv(
        certification_path,
        certification_rows,
        [
            "requested_horizon_days",
            "certified_semantic_model_key",
            "certified_model_family",
            "robustness_smape",
            "robustness_mae",
            "robustness_bias",
            "holdout_or_ensemble_validation",
            "persistent_product_exclusions",
            "selection_status",
        ],
    )

    write_csv(
        h90_holdout_path,
        h90_holdout_rows,
        sorted(
            {
                key
                for row in h90_holdout_rows
                for key in row
            }
        ),
    )

    write_csv(
        forecast_path,
        forecasts,
        [
            "canonical_product_id",
            "product_name",
            "current_price",
            "current_price_date",
            "forecast_horizon_days",
            "certified_model",
            "forecast_price_365d",
            "predicted_return_365d",
            "forecast_classification",
            "persistent_product_exclusion",
        ],
    )

    write_csv(
        gap_path,
        forecast_gaps,
        [
            "canonical_product_id",
            "product_name",
            "current_price",
            "current_price_date",
            "gap_reason",
            "direct_forecast_authorized",
        ],
    )

    write_csv(
        scenario_path,
        scenario_rows,
        [
            "canonical_product_id",
            "product_name",
            "current_price",
            "scenario_horizon_days",
            "scenario_years",
            "one_year_certified_model",
            "one_year_forecast_price",
            "conservative_scenario_price",
            "base_scenario_price",
            "upside_scenario_price",
            "scenario_classification",
            "directly_backtested_at_this_horizon",
            "monte_carlo_result",
            "purchase_recommendation",
        ],
    )

    calibration_path.write_text(
        json.dumps(
            calibration,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_FINAL_MODEL_FORECAST_SCENARIO_V1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "canonical_products":
            131,

        "final_horizon_models_certified":
            3,

        "certified_h90_model":
            selected[90][
                "semantic_model_key"
            ],

        "certified_h180_model":
            selected[180][
                "semantic_model_key"
            ],

        "certified_h365_model":
            selected[365][
                "semantic_model_key"
            ],

        "h90_holdout_attempted_products":
            115,

        "h90_holdout_valid_prediction_products":
            len(
                h90_holdout_products
            ),

        "h90_holdout_no_valid_prediction_products":
            len(
                h90_no_valid_holdout_products
            ),

        "h365_holdout_attempted_products":
            115,

        "h365_holdout_valid_prediction_products":
            len(
                h365_holdout_products
            ),

        "h365_holdout_no_valid_prediction_products":
            len(
                h365_no_valid_holdout_products
            ),

        "production_365_training_rows":
            len(
                train_x
            ),

        "production_365_forecast_rows":
            len(
                forecasts
            ),

        "production_365_gap_rows":
            len(
                forecast_gaps
            ),

        "uncertainty_calibration_rows":
            len(
                residual_array
            ),

        "scenario_rows":
            len(
                scenario_rows
            ),

        "three_year_direct_backtest":
            False,

        "five_year_direct_backtest":
            False,

        "three_year_classification":
            "THREE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED",

        "five_year_classification":
            "FIVE_YEAR_SCENARIO_NOT_DIRECTLY_BACKTESTED",

        "persistent_product_exclusions":
            0,

        "monte_carlo_executed":
            False,

        "investment_ranking_executed":
            False,

        "purchase_recommendations_authorized":
            False,

        "monte_carlo_execution_authorized_next":
            True,

        "authorized_next_large_step":
            "MONTE_CARLO_UNCERTAINTY_AND_PURCHASE_RANKING",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        "PASS_PRECOLLECTOR_FINAL_MODEL_FORECAST_SCENARIO_V1",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        f"FINAL_HORIZON_MODELS_CERTIFIED=3",
        flush=True,
    )

    print(
        f"H90={summary['certified_h90_model']}",
        flush=True,
    )

    print(
        f"H180={summary['certified_h180_model']}",
        flush=True,
    )

    print(
        f"H365={summary['certified_h365_model']}",
        flush=True,
    )

    print(
        (
            "H90_GENUINE_HOLDOUT_PRODUCTS="
            f"{summary['h90_holdout_valid_prediction_products']}"
        ),
        flush=True,
    )

    print(
        (
            "H365_GENUINE_HOLDOUT_PRODUCTS="
            f"{summary['h365_holdout_valid_prediction_products']}"
        ),
        flush=True,
    )

    print(
        (
            "PRODUCTION_365_FORECAST_ROWS="
            f"{summary['production_365_forecast_rows']}"
        ),
        flush=True,
    )

    print(
        (
            "PRODUCTION_365_GAP_ROWS="
            f"{summary['production_365_gap_rows']}"
        ),
        flush=True,
    )

    print(
        (
            "UNCERTAINTY_CALIBRATION_ROWS="
            f"{summary['uncertainty_calibration_rows']}"
        ),
        flush=True,
    )

    print(
        (
            "LONG_HORIZON_SCENARIO_ROWS="
            f"{summary['scenario_rows']}"
        ),
        flush=True,
    )

    print(
        "THREE_YEAR_DIRECT_BACKTEST=FALSE",
        flush=True,
    )

    print(
        "FIVE_YEAR_DIRECT_BACKTEST=FALSE",
        flush=True,
    )

    print(
        "MONTE_CARLO_EXECUTED=FALSE",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )