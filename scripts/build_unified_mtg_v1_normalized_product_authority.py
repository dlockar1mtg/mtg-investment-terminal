from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "mtg_asset_id",
    "mtg_lane",
    "native_asset_id",
    "product_name",
    "lane_authority_state",
    "current_price_usd",
    "current_price_authority_available",
    "forecast_authority_available",
    "forecast_1y_price_usd",
    "forecast_1y_return",
    "risk_authority_available",
    "native_rank",
    "native_rank_type",
    "native_purchase_status",
    "purchase_semantic",
    "evidence_state",
    "actionability_state",
    "execution_ready_purchase_certified",
    "manual_execution_price_check_required",
    "native_authority_pointer",
    "native_authority_sha256",
    "snapshot_population_is_permanent",
    "automatic_purchase_execution",
]


def fail(message: str) -> None:
    raise RuntimeError("FAIL-CLOSED: " + message)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def b(value: bool) -> str:
    return "true" if value else "false"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def first(
    row: dict[str, str],
    names: list[str],
    *,
    required: bool = False,
    label: str = "",
) -> str:

    for name in names:

        if name in row:

            value = clean(
                row.get(name)
            )

            if value:
                return value

    if required:
        fail(
            "missing required field/value for "
            + label
            + "; candidates="
            + repr(names)
        )

    return ""


def unique_index(
    rows: list[dict[str, str]],
    field: str,
    label: str,
) -> dict[str, dict[str, str]]:

    result: dict[str, dict[str, str]] = {}

    for row in rows:

        key = clean(
            row.get(field)
        )

        if not key:
            fail(
                "blank "
                + label
                + " id"
            )

        if key in result:
            fail(
                "duplicate "
                + label
                + " id: "
                + key
            )

        result[key] = row

    return result


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
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
            fieldnames=FIELDS,
            extrasaction="raise",
        )

        writer.writeheader()
        writer.writerows(rows)


parser = argparse.ArgumentParser()

parser.add_argument(
    "--collector-current",
    required=True,
)

parser.add_argument(
    "--collector-ranking",
    required=True,
)

parser.add_argument(
    "--collector-purchase",
    required=True,
)

parser.add_argument(
    "--pre-current",
    required=True,
)

parser.add_argument(
    "--pre-price-gaps",
    required=True,
)

parser.add_argument(
    "--pre-disposition",
    required=True,
)

parser.add_argument(
    "--pre-monte-carlo",
    required=True,
)

parser.add_argument(
    "--pre-purchase",
    required=True,
)

parser.add_argument(
    "--secret-ranking",
    required=True,
)

parser.add_argument(
    "--secret-purchase",
    required=True,
)

parser.add_argument(
    "--secret-actionability",
    required=True,
)

parser.add_argument(
    "--output",
    required=True,
)

parser.add_argument(
    "--summary",
    required=True,
)

parser.add_argument(
    "--collector-current-sha",
    required=True,
)

parser.add_argument(
    "--collector-purchase-sha",
    required=True,
)

parser.add_argument(
    "--pre-current-sha",
    required=True,
)

parser.add_argument(
    "--pre-disposition-sha",
    required=True,
)

parser.add_argument(
    "--secret-actionability-sha",
    required=True,
)


args = parser.parse_args()


collector_current_path = Path(
    args.collector_current
)

collector_ranking_path = Path(
    args.collector_ranking
)

collector_purchase_path = Path(
    args.collector_purchase
)

pre_current_path = Path(
    args.pre_current
)

pre_price_gaps_path = Path(
    args.pre_price_gaps
)

pre_disposition_path = Path(
    args.pre_disposition
)

pre_monte_carlo_path = Path(
    args.pre_monte_carlo
)

pre_purchase_path = Path(
    args.pre_purchase
)

secret_ranking_path = Path(
    args.secret_ranking
)

secret_purchase_path = Path(
    args.secret_purchase
)

secret_actionability_path = Path(
    args.secret_actionability
)

output_path = Path(
    args.output
)

summary_path = Path(
    args.summary
)


# ============================================================================
# COLLECTOR
# ============================================================================

collector_current = read_csv(
    collector_current_path
)

collector_ranking = read_csv(
    collector_ranking_path
)

collector_purchase = read_csv(
    collector_purchase_path
)


if len(collector_current) != 50:
    fail(
        "Collector current rows != 50"
    )

if len(collector_ranking) != 49:
    fail(
        "Collector ranking rows != 49"
    )

if len(collector_purchase) != 49:
    fail(
        "Collector purchase rows != 49"
    )


collector_rank_by_id = unique_index(
    collector_ranking,
    "canonical_product_id",
    "Collector ranking",
)

collector_purchase_by_id = unique_index(
    collector_purchase,
    "canonical_product_id",
    "Collector purchase",
)


collector_rows: list[
    dict[str, str]
] = []

collector_current_ids: set[str] = set()

collector_ranked = 0
collector_unranked = 0


for source in collector_current:

    native_id = first(
        source,
        [
            "canonical_product_id",
            "tcgplayer_product_id",
            "product_id",
        ],
        required=True,
        label="Collector asset id",
    )

    if native_id in collector_current_ids:
        fail(
            "duplicate Collector current ID: "
            + native_id
        )

    collector_current_ids.add(
        native_id
    )

    product_name = first(
        source,
        [
            "product_name",
            "name",
        ],
        required=True,
        label=(
            "Collector product name "
            + native_id
        ),
    )

    current_price = first(
        source,
        [
            "current_price",
            "current_market_price",
            "market_price",
            "price",
        ],
        required=True,
        label=(
            "Collector current price "
            + native_id
        ),
    )

    rank_row = collector_rank_by_id.get(
        native_id
    )

    purchase_row = collector_purchase_by_id.get(
        native_id
    )

    if (
        (rank_row is None)
        !=
        (purchase_row is None)
    ):
        fail(
            "Collector ranking/purchase "
            "membership mismatch: "
            + native_id
        )


    if purchase_row is None:

        collector_unranked += 1

        native_rank = ""
        purchase_status = ""
        forecast_price = ""
        forecast_return = ""
        risk_available = False
        forecast_available = False

        evidence_state = (
            "CURRENT_PRICE_AUTHORITY_ONLY"
        )

        actionability_state = (
            "UNRANKED_NATIVE_COLLECTOR_ASSET"
        )

        native_pointer = (
            "repository:"
            "data/governance/permanence/"
            "certification/"
            "collector_v1_final_premodel_"
            "user_exclusion_resolution/"
            "collector_final_current_price_"
            "authority.csv"
        )

        native_hash = (
            args.collector_current_sha
        )

    else:

        collector_ranked += 1

        native_rank = clean(
            rank_row.get(
                "final_rank"
            )
        )

        purchase_status = clean(
            purchase_row.get(
                "purchase_status"
            )
        )

        forecast_price = clean(
            purchase_row.get(
                "median_price_365"
            )
        )

        forecast_return = clean(
            purchase_row.get(
                "median_return_365"
            )
        )

        forecast_available = bool(
            forecast_price
            or
            forecast_return
        )

        risk_available = bool(
            clean(
                purchase_row.get(
                    "probability_of_loss_365"
                )
            )
        )

        evidence_state = clean(
            purchase_row.get(
                "final_ranking_eligibility_status"
            )
        )

        if not evidence_state:

            evidence_state = clean(
                rank_row.get(
                    "final_ranking_eligibility_status"
                )
            )

        actionability_state = (
            purchase_status
            if purchase_status
            else
            "NATIVE_COLLECTOR_PURCHASE_AUTHORITY_PRESENT"
        )

        native_pointer = (
            "repository:"
            "data/governance/permanence/"
            "certification/"
            "collector_v1_purchase_"
            "recommendation_certification/"
            "collector_purchase_"
            "recommendation_authority.csv"
        )

        native_hash = (
            args.collector_purchase_sha
        )


    collector_rows.append(
        {
            "mtg_asset_id":
                "COLLECTOR_V1|"
                + native_id,

            "mtg_lane":
                "COLLECTOR_V1",

            "native_asset_id":
                native_id,

            "product_name":
                product_name,

            "lane_authority_state":
                "CERTIFIED_CLOSED",

            "current_price_usd":
                current_price,

            "current_price_authority_available":
                "true",

            "forecast_authority_available":
                b(
                    forecast_available
                ),

            "forecast_1y_price_usd":
                forecast_price,

            "forecast_1y_return":
                forecast_return,

            "risk_authority_available":
                b(
                    risk_available
                ),

            "native_rank":
                native_rank,

            "native_rank_type":
                (
                    "COLLECTOR_FINAL_GOVERNED_RANK"
                    if native_rank
                    else ""
                ),

            "native_purchase_status":
                purchase_status,

            "purchase_semantic":
                (
                    "NATIVE_COLLECTOR_PURCHASE_STATUS"
                    if purchase_status
                    else ""
                ),

            "evidence_state":
                evidence_state,

            "actionability_state":
                actionability_state,

            "execution_ready_purchase_certified":
                "false",

            "manual_execution_price_check_required":
                "true",

            "native_authority_pointer":
                native_pointer,

            "native_authority_sha256":
                native_hash,

            "snapshot_population_is_permanent":
                "false",

            "automatic_purchase_execution":
                "false",
        }
    )


if collector_ranked != 49:
    fail(
        "Collector normalized ranked rows != 49"
    )

if collector_unranked != 1:
    fail(
        "Collector normalized unranked rows != 1"
    )


# ============================================================================
# PRE-COLLECTOR
# ============================================================================

pre_current = read_csv(
    pre_current_path
)

pre_price_gaps = read_csv(
    pre_price_gaps_path
)

pre_disposition = read_csv(
    pre_disposition_path
)

pre_monte_carlo = read_csv(
    pre_monte_carlo_path
)

pre_purchase = read_csv(
    pre_purchase_path
)


if len(pre_current) != 121:
    fail(
        "Pre-Collector current-price rows != 121"
    )

if len(pre_price_gaps) != 10:
    fail(
        "Pre-Collector current-price gap rows != 10"
    )

if len(pre_disposition) != 131:
    fail(
        "Pre-Collector disposition rows != 131"
    )

if len(pre_monte_carlo) != 190:
    fail(
        "Pre-Collector Monte Carlo rows != 190"
    )

if len(pre_purchase) != 95:
    fail(
        "Pre-Collector purchase rows != 95"
    )


pre_current_by_id = unique_index(
    pre_current,
    "canonical_product_id",
    "Pre-Collector current price",
)

pre_gap_by_id = unique_index(
    pre_price_gaps,
    "canonical_product_id",
    "Pre-Collector current price gap",
)

pre_purchase_by_id = unique_index(
    pre_purchase,
    "canonical_product_id",
    "Pre-Collector purchase",
)


pre_disposition_by_id = unique_index(
    pre_disposition,
    "canonical_product_id",
    "Pre-Collector disposition",
)


pre_disposition_ids = set(
    pre_disposition_by_id.keys()
)

pre_current_ids = set(
    pre_current_by_id.keys()
)

pre_gap_ids = set(
    pre_gap_by_id.keys()
)


if (
    pre_current_ids
    &
    pre_gap_ids
):
    fail(
        "Pre-Collector current/gap IDs overlap"
    )


if (
    pre_current_ids
    |
    pre_gap_ids
) != pre_disposition_ids:
    fail(
        "Pre-Collector 121 price + 10 gap "
        "IDs do not exactly equal the "
        "131-product disposition universe"
    )


pre_purchase_ids = set(
    pre_purchase_by_id.keys()
)


if not pre_purchase_ids.issubset(
    pre_current_ids
):
    fail(
        "A ranked Pre-Collector product "
        "lacks current-price authority"
    )


pre_mc_by_id: dict[
    str,
    list[dict[str, str]]
] = {}


for row in pre_monte_carlo:

    key = clean(
        row.get(
            "canonical_product_id"
        )
    )

    if not key:
        fail(
            "blank Pre-Collector Monte Carlo ID"
        )

    pre_mc_by_id.setdefault(
        key,
        [],
    ).append(
        row
    )


if set(
    pre_mc_by_id.keys()
) != pre_purchase_ids:
    fail(
        "Pre-Collector Monte Carlo and "
        "purchase product sets differ"
    )


for key, rows in pre_mc_by_id.items():

    if len(rows) != 2:
        fail(
            "Pre-Collector Monte Carlo "
            "product does not have two "
            "scenario horizons: "
            + key
        )


forecast_gap_ids = (
    pre_current_ids
    -
    pre_purchase_ids
)


if len(
    forecast_gap_ids
) != 26:
    fail(
        "Pre-Collector governed forecast-gap "
        "set != 26"
    )


if len(
    pre_gap_ids
) != 10:
    fail(
        "Pre-Collector governed no-current "
        "set != 10"
    )


pre_rows: list[
    dict[str, str]
] = []

pre_ranked = 0
pre_forecast_gaps = 0
pre_no_current = 0


for native_id in sorted(
    pre_disposition_ids
):

    source = pre_disposition_by_id[
        native_id
    ]

    product_name = clean(
        source.get(
            "product_name"
        )
    )

    if not product_name:
        fail(
            "blank Pre-Collector product name: "
            + native_id
        )

    final_status = clean(
        source.get(
            "final_analysis_status"
        )
    )

    not_ranked_reason = clean(
        source.get(
            "not_ranked_reason"
        )
    )

    current_row = pre_current_by_id.get(
        native_id
    )

    purchase_row = pre_purchase_by_id.get(
        native_id
    )


    if current_row is None:

        if native_id not in pre_gap_ids:
            fail(
                "Pre-Collector product absent from "
                "both price and gap authority: "
                + native_id
            )

        pre_no_current += 1

        current_price = ""

        current_available = False

    else:

        current_price = clean(
            current_row.get(
                "selected_price"
            )
        )

        if not current_price:
            fail(
                "blank governed Pre-Collector price: "
                + native_id
            )

        try:

            parsed_current_price = float(
                current_price
            )

        except Exception as exc:

            fail(
                "invalid governed Pre-Collector "
                "price for "
                + native_id
                + ": "
                + str(exc)
            )

        if parsed_current_price <= 0:
            fail(
                "non-positive governed "
                "Pre-Collector price: "
                + native_id
            )

        current_available = True


    if purchase_row is None:

        native_rank = ""
        native_purchase_status = ""
        forecast_price = ""
        forecast_return = ""
        forecast_available = False
        risk_available = False

        evidence_state = (
            not_ranked_reason
            if not_ranked_reason
            else final_status
        )

        actionability_state = (
            final_status
            if final_status
            else "NOT_RANKED"
        )

        if current_available:

            pre_forecast_gaps += 1

            if native_id not in forecast_gap_ids:
                fail(
                    "Unexpected Pre-Collector "
                    "unranked current-price product: "
                    + native_id
                )

        else:

            if native_id not in pre_gap_ids:
                fail(
                    "Unexpected Pre-Collector "
                    "no-current product: "
                    + native_id
                )

    else:

        pre_ranked += 1

        if not current_available:
            fail(
                "Ranked Pre-Collector product "
                "lacks governed current price: "
                + native_id
            )

        native_rank = clean(
            purchase_row.get(
                "purchase_rank"
            )
        )

        if not native_rank:
            fail(
                "Ranked Pre-Collector product "
                "missing purchase_rank: "
                + native_id
            )

        native_purchase_status = clean(
            purchase_row.get(
                "investment_tier"
            )
        )

        forecast_price = clean(
            purchase_row.get(
                "forecast_price_365d"
            )
        )

        if not forecast_price:
            fail(
                "Ranked Pre-Collector product "
                "missing 365d forecast price: "
                + native_id
            )

        try:

            forecast_return = str(
                (
                    float(
                        forecast_price
                    )
                    /
                    float(
                        current_price
                    )
                )
                - 1.0
            )

        except Exception as exc:

            fail(
                "Could not derive Pre-Collector "
                "1y return for "
                + native_id
                + ": "
                + str(exc)
            )

        forecast_available = True
        risk_available = True

        evidence_state = clean(
            purchase_row.get(
                "confidence_quartile"
            )
        )

        actionability_state = (
            final_status
            if final_status
            else "RANKED_FORECASTABLE"
        )


    pre_rows.append(
        {
            "mtg_asset_id":
                "PRE_COLLECTOR_V1|"
                + native_id,

            "mtg_lane":
                "PRE_COLLECTOR_V1",

            "native_asset_id":
                native_id,

            "product_name":
                product_name,

            "lane_authority_state":
                "CERTIFIED_CLOSED",

            "current_price_usd":
                current_price,

            "current_price_authority_available":
                b(
                    current_available
                ),

            "forecast_authority_available":
                b(
                    forecast_available
                ),

            "forecast_1y_price_usd":
                forecast_price,

            "forecast_1y_return":
                forecast_return,

            "risk_authority_available":
                b(
                    risk_available
                ),

            "native_rank":
                native_rank,

            "native_rank_type":
                (
                    "PRECOLLECTOR_PURCHASE_RANK"
                    if native_rank
                    else ""
                ),

            "native_purchase_status":
                native_purchase_status,

            "purchase_semantic":
                (
                    "PRECOLLECTOR_NATIVE_INVESTMENT_TIER"
                    if native_purchase_status
                    else ""
                ),

            "evidence_state":
                evidence_state,

            "actionability_state":
                actionability_state,

            "execution_ready_purchase_certified":
                "false",

            "manual_execution_price_check_required":
                "true",

            "native_authority_pointer":
                (
                    "certified_package:"
                    "MTG_PreCollector_Current_Price_"
                    "Authority_v2_20260808_151353.zip#"
                    "precollector_current_price_"
                    "authority_v2.csv"
                    if current_available
                    else
                    "certified_package:"
                    "MTG_PreCollector_Monte_Carlo_"
                    "Purchase_Ranking_v1_"
                    "20260809_111303.zip#"
                    "precollector_final_131_product_"
                    "disposition_v1.csv"
                ),

            "native_authority_sha256":
                (
                    args.pre_current_sha
                    if current_available
                    else
                    args.pre_disposition_sha
                ),

            "snapshot_population_is_permanent":
                "true",

            "automatic_purchase_execution":
                "false",
        }
    )


if pre_ranked != 95:
    fail(
        "Pre-Collector normalized ranked rows != 95"
    )

if pre_forecast_gaps != 26:
    fail(
        "Pre-Collector normalized forecast gaps != 26"
    )

if pre_no_current != 10:
    fail(
        "Pre-Collector normalized no-current rows != 10"
    )

if len(pre_rows) != 131:
    fail(
        "Pre-Collector normalized rows != 131"
    )


# ============================================================================
# SECRET LAIR V1.1
# ============================================================================

secret_ranking = read_csv(
    secret_ranking_path
)

secret_purchase = read_csv(
    secret_purchase_path
)

secret_actionability = read_csv(
    secret_actionability_path
)


if len(secret_ranking) != 787:
    fail(
        "Secret Lair ranking rows != 787"
    )

if len(secret_purchase) != 787:
    fail(
        "Secret Lair purchase rows != 787"
    )

if len(secret_actionability) != 787:
    fail(
        "Secret Lair actionability rows != 787"
    )


secret_rank_by_id = unique_index(
    secret_ranking,
    "secret_lair_id",
    "Secret Lair ranking",
)

secret_purchase_by_id = unique_index(
    secret_purchase,
    "secret_lair_id",
    "Secret Lair purchase",
)


secret_actionability_by_id = unique_index(
    secret_actionability,
    "secret_lair_id",
    "Secret Lair actionability",
)


if (
    set(
        secret_rank_by_id.keys()
    )
    !=
    set(
        secret_purchase_by_id.keys()
    )
    or
    set(
        secret_rank_by_id.keys()
    )
    !=
    set(
        secret_actionability_by_id.keys()
    )
):
    fail(
        "Secret Lair rank/purchase/"
        "actionability product sets differ"
    )


secret_rows: list[
    dict[str, str]
] = []


for native_id in sorted(
    secret_actionability_by_id.keys()
):

    source = (
        secret_actionability_by_id[
            native_id
        ]
    )

    purchase = (
        secret_purchase_by_id[
            native_id
        ]
    )

    product_name = clean(
        source.get(
            "product_name"
        )
    )

    if not product_name:
        fail(
            "blank Secret Lair product name: "
            + native_id
        )

    current_price = clean(
        source.get(
            "current_tcg_market_price_usd"
        )
    )

    forecast_price = clean(
        purchase.get(
            "certified_1y_point_forecast_usd"
        )
    )

    forecast_return = clean(
        purchase.get(
            "certified_1y_point_return"
        )
    )

    native_rank = clean(
        source.get(
            "v1_1_production_competition_rank"
        )
    )

    recommendation = clean(
        source.get(
            "purchase_recommendation"
        )
    )

    purchase_semantic = clean(
        source.get(
            "purchase_recommendation_semantic_class"
        )
    )

    evidence_class = clean(
        source.get(
            "own_history_evidence_class"
        )
    )

    evidence_qualifier = clean(
        source.get(
            "evidence_qualifier"
        )
    )

    evidence_state = evidence_class

    if evidence_qualifier:

        evidence_state = (
            evidence_state
            + "|"
            + evidence_qualifier
            if evidence_state
            else evidence_qualifier
        )


    execution_ready = (
        clean(
            source.get(
                "execution_ready_purchase_certified"
            )
        ).lower()
        == "true"
    )

    manual_check = (
        clean(
            source.get(
                "manual_execution_price_check_required"
            )
        ).lower()
        == "true"
    )


    if execution_ready:
        fail(
            "Secret Lair unexpectedly "
            "execution-ready: "
            + native_id
        )


    secret_rows.append(
        {
            "mtg_asset_id":
                "SECRET_LAIR_V1_1|"
                + native_id,

            "mtg_lane":
                "SECRET_LAIR_V1_1",

            "native_asset_id":
                native_id,

            "product_name":
                product_name,

            "lane_authority_state":
                "CERTIFIED_CLOSED",

            "current_price_usd":
                current_price,

            "current_price_authority_available":
                b(
                    bool(
                        current_price
                    )
                ),

            "forecast_authority_available":
                b(
                    bool(
                        forecast_price
                    )
                ),

            "forecast_1y_price_usd":
                forecast_price,

            "forecast_1y_return":
                forecast_return,

            "risk_authority_available":
                b(
                    bool(
                        clean(
                            purchase.get(
                                "y1_probability_of_loss"
                            )
                        )
                    )
                ),

            "native_rank":
                native_rank,

            "native_rank_type":
                "SECRET_LAIR_V1_1_PRODUCTION_COMPETITION_RANK",

            "native_purchase_status":
                recommendation,

            "purchase_semantic":
                purchase_semantic,

            "evidence_state":
                evidence_state,

            "actionability_state":
                purchase_semantic,

            "execution_ready_purchase_certified":
                "false",

            "manual_execution_price_check_required":
                b(
                    manual_check
                ),

            "native_authority_pointer":
                (
                    "repository:"
                    "docs/phase_8/"
                    "secret_lair_v1_1/"
                    "secret_lair_v1_1_"
                    "purchase_actionability.csv"
                ),

            "native_authority_sha256":
                args.secret_actionability_sha,

            "snapshot_population_is_permanent":
                "false",

            "automatic_purchase_execution":
                "false",
        }
    )


# ============================================================================
# UNIFIED VALIDATION
# ============================================================================

all_rows = (
    collector_rows
    +
    pre_rows
    +
    secret_rows
)


if len(all_rows) != 968:
    fail(
        "Unified normalized rows != 968"
    )


asset_ids = [
    row["mtg_asset_id"]
    for row in all_rows
]


if len(
    set(
        asset_ids
    )
) != len(
    asset_ids
):
    fail(
        "duplicate Unified MTG asset ID"
    )


lane_counts: dict[
    str,
    int
] = {}


for row in all_rows:

    lane = row[
        "mtg_lane"
    ]

    lane_counts[
        lane
    ] = (
        lane_counts.get(
            lane,
            0,
        )
        + 1
    )


expected_lane_counts = {
    "COLLECTOR_V1": 50,
    "PRE_COLLECTOR_V1": 131,
    "SECRET_LAIR_V1_1": 787,
}


if lane_counts != expected_lane_counts:
    fail(
        "Unified lane counts mismatch: "
        + repr(
            lane_counts
        )
    )


for row in all_rows:

    if (
        row[
            "automatic_purchase_execution"
        ]
        !=
        "false"
    ):
        fail(
            "automatic purchase execution detected"
        )

    if (
        row[
            "execution_ready_purchase_certified"
        ]
        !=
        "false"
    ):
        fail(
            "execution-ready purchase unexpectedly certified"
        )

    if (
        row[
            "current_price_authority_available"
        ]
        ==
        "false"
        and
        row[
            "current_price_usd"
        ]
    ):
        fail(
            "price present while price authority false: "
            + row[
                "mtg_asset_id"
            ]
        )

    if (
        row[
            "forecast_authority_available"
        ]
        ==
        "false"
        and
        (
            row[
                "forecast_1y_price_usd"
            ]
            or
            row[
                "forecast_1y_return"
            ]
        )
    ):
        fail(
            "forecast value present while forecast authority false: "
            + row[
                "mtg_asset_id"
            ]
        )


all_rows.sort(
    key=lambda row: (
        row[
            "mtg_lane"
        ],
        row[
            "native_asset_id"
        ],
    )
)


write_csv(
    output_path,
    all_rows,
)


summary = {
    "status":
        "UNIFIED_MTG_V1_NORMALIZED_PRODUCT_AUTHORITY_ASSEMBLED",

    "assembly_revision":
        "U1C_R1",

    "row_grain":
        "ONE_ROW_PER_GOVERNED_MTG_ASSET_PER_AUTHORITY_SNAPSHOT",

    "current_snapshot": {
        "total_rows":
            968,

        "collector_rows":
            50,

        "precollector_rows":
            131,

        "secret_lair_rows":
            787,

        "snapshot_total_is_permanent_universe_constant":
            False,
    },

    "collector": {
        "ranked_rows":
            collector_ranked,

        "unranked_rows":
            collector_unranked,
    },

    "precollector": {
        "canonical_rows":
            131,

        "current_price_authority_rows":
            len(
                pre_current_ids
            ),

        "no_current_price_authority_rows":
            len(
                pre_gap_ids
            ),

        "ranked_forecastable_rows":
            pre_ranked,

        "forecast_gap_rows_with_current_price":
            pre_forecast_gaps,

        "current_price_source":
            "CERTIFIED_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_V2",

        "disposition_current_price_field_used":
            False,

        "price_reconciliation":
            "121_EQUALS_95_PLUS_26",
    },

    "secret_lair": {
        "current_ranked_snapshot_rows":
            787,

        "dynamic_universe":
            True,

        "fixed_product_count":
            False,
    },

    "governance": {
        "native_methods_preserved":
            True,

        "cross_lane_rank_created":
            False,

        "cross_lane_score_created":
            False,

        "cross_lane_purchase_policy_created":
            False,

        "missing_price_values_synthesized":
            0,

        "missing_forecast_values_synthesized":
            0,

        "models_rerun":
            False,

        "marketplace_calls":
            0,

        "automatic_purchase_execution":
            False,
    },

    "output": {
        "path":
            "docs/phase_9/unified_mtg/"
            "unified_mtg_v1_normalized_product_authority.csv",

        "sha256":
            sha256(
                output_path
            ),
    },

    "next_gate":
        "MTG_U1D_NORMALIZED_AUTHORITY_VALIDATION_AND_PRODUCTION_CERTIFICATION",
}


summary_path.parent.mkdir(
    parents=True,
    exist_ok=True,
)

summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "MTG_U1C_R1=PASS"
)

print(
    "UNIFIED_ROWS=968"
)

print(
    "COLLECTOR_ROWS=50"
)

print(
    "PRECOLLECTOR_ROWS=131"
)

print(
    "SECRET_LAIR_ROWS=787"
)

print(
    "PRECOLLECTOR_CURRENT_PRICE_ROWS=121"
)

print(
    "PRECOLLECTOR_NO_CURRENT_PRICE_ROWS=10"
)

print(
    "PRECOLLECTOR_RANKED_ROWS=95"
)

print(
    "PRECOLLECTOR_FORECAST_GAP_ROWS=26"
)

print(
    "PRECOLLECTOR_PRICE_RECONCILIATION_121_EQUALS_95_PLUS_26=TRUE"
)

print(
    "DISPOSITION_CURRENT_PRICE_FIELD_USED=FALSE"
)

print(
    "CROSS_LANE_RANK_CREATED=FALSE"
)

print(
    "AUTOMATIC_PURCHASE_EXECUTION=FALSE"
)

print(
    "OUTPUT_SHA256="
    + sha256(
        output_path
    )
)

print(
    "NEXT_GATE="
    "MTG_U1D_NORMALIZED_AUTHORITY_VALIDATION_AND_PRODUCTION_CERTIFICATION"
)