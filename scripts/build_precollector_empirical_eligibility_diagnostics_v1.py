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


EXPECTED_CANONICAL = 131
EXPECTED_HISTORY = 115
EXPECTED_CURRENT = 121
EXPECTED_AVAILABILITY = 111


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def number(value: object) -> float | None:

    try:
        parsed = float(clean(value))
    except (TypeError, ValueError):
        return None

    if not math.isfinite(parsed):
        return None

    return parsed


def sha256_file(path: Path) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        for block in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

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
        writer.writerows(rows)


def parse_date(value: object) -> date | None:

    text = clean(value)

    if not text:
        return None

    try:
        return date.fromisoformat(
            text[:10]
        )
    except ValueError:
        return None


def percentile(
    values: list[float],
    p: float,
) -> float | None:

    if not values:
        return None

    values = sorted(values)

    if len(values) == 1:
        return values[0]

    position = (
        len(values) - 1
    ) * p

    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return values[lower]

    weight = (
        position - lower
    )

    return (
        values[lower]
        * (1.0 - weight)
        + values[upper]
        * weight
    )


def log_return_volatility(
    prices: list[float],
) -> float | None:

    if len(prices) < 3:
        return None

    returns = []

    for previous, current in zip(
        prices[:-1],
        prices[1:],
    ):

        if (
            previous <= 0
            or current <= 0
        ):
            continue

        returns.append(
            math.log(
                current / previous
            )
        )

    if len(returns) < 2:
        return None

    return statistics.stdev(
        returns
    )


def maximum_drawdown(
    prices: list[float],
) -> float | None:

    if not prices:
        return None

    peak = prices[0]
    worst = 0.0

    for value in prices:

        if value > peak:
            peak = value

        if peak <= 0:
            continue

        drawdown = (
            value / peak
        ) - 1.0

        if drawdown < worst:
            worst = drawdown

    return worst


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--universe-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--history-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--current-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--availability-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--expected-identity-sha",
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    # ========================================================================
    # Universe
    # ========================================================================

    universe = read_zip_csv(
        args.universe_package,
        "precollector_canonical_universe_v2.csv",
    )

    if len(universe) != EXPECTED_CANONICAL:
        fail(
            f"universe count {len(universe)} != 131"
        )

    canonical = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
            row
        for row in universe
    }

    if len(canonical) != EXPECTED_CANONICAL:
        fail(
            "canonical IDs are not unique"
        )

    identity_material = "\n".join(
        f"{row['canonical_product_id']}|{row['product_name']}"
        for row in sorted(
            universe,
            key=lambda row: int(
                clean(
                    row[
                        "canonical_product_id"
                    ]
                ).split(":")[-1]
            ),
        )
    ) + "\n"

    identity_sha = hashlib.sha256(
        identity_material.encode(
            "utf-8"
        )
    ).hexdigest()

    if identity_sha != args.expected_identity_sha:
        fail(
            "canonical identity SHA mismatch"
        )

    # ========================================================================
    # Historical authority
    # ========================================================================

    history = read_zip_csv(
        args.history_package,
        "precollector_historical_price_authority_v3.csv",
    )

    history_coverage = read_zip_csv(
        args.history_package,
        "precollector_historical_price_coverage_v3.csv",
    )

    history_by_product: dict[
        str,
        list[dict[str, str]],
    ] = defaultdict(list)

    for row in history:

        canonical_id = clean(
            row[
                "canonical_product_id"
            ]
        )

        if canonical_id not in canonical:
            fail(
                "history contains noncanonical ID"
            )

        history_by_product[
            canonical_id
        ].append(row)

    if len(history_by_product) != EXPECTED_HISTORY:
        fail(
            "historical coverage is not 115 products"
        )

    if len(history_coverage) != 131:
        fail(
            "historical coverage ledger is not 131 rows"
        )

    # ========================================================================
    # Current price authority
    # ========================================================================

    current = read_zip_csv(
        args.current_package,
        "precollector_current_price_authority_v2.csv",
    )

    current_coverage = read_zip_csv(
        args.current_package,
        "precollector_current_price_coverage_v2.csv",
    )

    current_by_product = {
        clean(
            row[
                "canonical_product_id"
            ]
        ): row
        for row in current
    }

    if len(current_by_product) != EXPECTED_CURRENT:
        fail(
            "current-price coverage is not 121 products"
        )

    if len(current_coverage) != 131:
        fail(
            "current-price coverage ledger is not 131 rows"
        )

    current_dates = {
        parse_date(
            row.get(
                "observation_date"
            )
        )
        for row in current
    }

    current_dates.discard(
        None
    )

    if len(current_dates) != 1:
        fail(
            "current-price authority does not have one operating date"
        )

    operating_date = next(
        iter(current_dates)
    )

    # ========================================================================
    # Availability authority
    # ========================================================================

    availability = read_zip_csv(
        args.availability_package,
        "precollector_availability_authority_v1.csv",
    )

    availability_coverage = read_zip_csv(
        args.availability_package,
        "precollector_availability_coverage_v1.csv",
    )

    availability_by_product: dict[
        str,
        list[dict[str, str]],
    ] = defaultdict(list)

    for row in availability:

        canonical_id = clean(
            row[
                "canonical_product_id"
            ]
        )

        if canonical_id not in canonical:
            fail(
                "availability contains noncanonical ID"
            )

        availability_by_product[
            canonical_id
        ].append(row)

    if (
        len(
            availability_by_product
        )
        != EXPECTED_AVAILABILITY
    ):
        fail(
            "availability coverage is not 111 products"
        )

    if len(availability_coverage) != 131:
        fail(
            "availability coverage ledger is not 131 rows"
        )

    # ========================================================================
    # Build empirical diagnostics
    # ========================================================================

    diagnostics = []

    for canonical_id in sorted(
        canonical,
        key=lambda value: int(
            value.split(":")[-1]
        ),
    ):

        identity = canonical[
            canonical_id
        ]

        # --------------------------------------------------------------------
        # History
        # --------------------------------------------------------------------

        history_rows = sorted(
            history_by_product.get(
                canonical_id,
                [],
            ),
            key=lambda row: (
                clean(
                    row.get(
                        "observation_date"
                    )
                )
            ),
        )

        historical_points = []

        for row in history_rows:

            observation_date = parse_date(
                row.get(
                    "observation_date"
                )
            )

            price = number(
                row.get(
                    "historical_price"
                )
            )

            if (
                observation_date is not None
                and price is not None
                and price > 0
            ):
                historical_points.append(
                    (
                        observation_date,
                        price,
                    )
                )

        historical_dates = [
            item[0]
            for item in historical_points
        ]

        historical_prices = [
            item[1]
            for item in historical_points
        ]

        history_count = len(
            historical_points
        )

        first_history_date = (
            historical_dates[0]
            if historical_dates
            else None
        )

        last_history_date = (
            historical_dates[-1]
            if historical_dates
            else None
        )

        history_span_days = (
            (
                last_history_date
                - first_history_date
            ).days
            if (
                first_history_date
                and last_history_date
            )
            else None
        )

        history_staleness_days = (
            (
                operating_date
                - last_history_date
            ).days
            if last_history_date
            else None
        )

        log_volatility = (
            log_return_volatility(
                historical_prices
            )
        )

        max_drawdown = (
            maximum_drawdown(
                historical_prices
            )
        )

        # --------------------------------------------------------------------
        # Current price
        # --------------------------------------------------------------------

        current_row = current_by_product.get(
            canonical_id
        )

        current_price = (
            number(
                current_row.get(
                    "selected_price"
                )
            )
            if current_row
            else None
        )

        # --------------------------------------------------------------------
        # Availability / liquidity
        # --------------------------------------------------------------------

        listings = availability_by_product.get(
            canonical_id,
            [],
        )

        sellers = {
            clean(
                row.get(
                    "seller_hash"
                )
            )
            for row in listings
            if clean(
                row.get(
                    "seller_hash"
                )
            )
        }

        landed_prices = []

        for row in listings:

            price = number(
                row.get(
                    "landed_price"
                )
            )

            if (
                price is not None
                and price > 0
            ):
                landed_prices.append(
                    price
                )

        listing_count = len(
            listings
        )

        seller_count = len(
            sellers
        )

        positive_price_count = len(
            landed_prices
        )

        ebay_median = (
            statistics.median(
                landed_prices
            )
            if landed_prices
            else None
        )

        ebay_stddev = (
            statistics.stdev(
                landed_prices
            )
            if len(landed_prices) >= 2
            else None
        )

        ebay_cv = (
            ebay_stddev / ebay_median
            if (
                ebay_stddev is not None
                and ebay_median is not None
                and ebay_median > 0
            )
            else None
        )

        q1 = percentile(
            landed_prices,
            0.25,
        )

        q3 = percentile(
            landed_prices,
            0.75,
        )

        ebay_iqr = (
            q3 - q1
            if (
                q1 is not None
                and q3 is not None
            )
            else None
        )

        # --------------------------------------------------------------------
        # Source disagreement
        #
        # eBay remains availability/reference evidence, NOT price authority.
        # --------------------------------------------------------------------

        source_difference = (
            current_price
            - ebay_median
            if (
                current_price is not None
                and ebay_median is not None
            )
            else None
        )

        source_pct_difference = (
            source_difference
            / ebay_median
            if (
                source_difference is not None
                and ebay_median is not None
                and ebay_median > 0
            )
            else None
        )

        # --------------------------------------------------------------------
        # Release-age descriptive variable.
        #
        # DESCRIPTIVE ONLY. Never an eligibility cutoff.
        # --------------------------------------------------------------------

        release_date = parse_date(
            identity.get(
                "canonical_release_date"
            )
        )

        product_age_days = (
            (
                operating_date
                - release_date
            ).days
            if release_date
            else None
        )

        # --------------------------------------------------------------------
        # Missingness
        # --------------------------------------------------------------------

        missing_history = (
            history_count == 0
        )

        missing_current = (
            current_price is None
        )

        missing_availability = (
            listing_count == 0
        )

        evidence_domains_present = sum(
            [
                not missing_history,
                not missing_current,
                not missing_availability,
            ]
        )

        diagnostics.append(
            {
                "canonical_product_id":
                    canonical_id,

                "tcgplayer_product_id":
                    canonical_id.split(":")[-1],

                "product_name":
                    clean(
                        identity[
                            "product_name"
                        ]
                    ),

                "canonical_release_date":
                    clean(
                        identity.get(
                            "canonical_release_date"
                        )
                    ),

                "product_age_days":
                    product_age_days
                    if product_age_days is not None
                    else "",

                # PRICE_HISTORY_COVERAGE
                "history_observation_count":
                    history_count,

                "history_distinct_date_count":
                    len(
                        set(
                            historical_dates
                        )
                    ),

                "history_first_date":
                    first_history_date.isoformat()
                    if first_history_date
                    else "",

                "history_last_date":
                    last_history_date.isoformat()
                    if last_history_date
                    else "",

                "history_span_days":
                    history_span_days
                    if history_span_days is not None
                    else "",

                # PRICE_HISTORY_STALENESS
                "history_staleness_days":
                    history_staleness_days
                    if history_staleness_days is not None
                    else "",

                # PRICE_PATH_STABILITY
                "historical_first_price":
                    historical_prices[0]
                    if historical_prices
                    else "",

                "historical_latest_price":
                    historical_prices[-1]
                    if historical_prices
                    else "",

                "historical_log_return_volatility":
                    log_volatility
                    if log_volatility is not None
                    else "",

                "historical_max_drawdown":
                    max_drawdown
                    if max_drawdown is not None
                    else "",

                # CURRENT PRICE
                "current_price_available":
                    str(
                        not missing_current
                    ).lower(),

                "tcgcsv_current_price":
                    current_price
                    if current_price is not None
                    else "",

                "current_price_observation_date":
                    operating_date.isoformat(),

                # CURRENT_AVAILABILITY / LIQUIDITY
                "availability_available":
                    str(
                        not missing_availability
                    ).lower(),

                "accepted_listing_count":
                    listing_count,

                "unique_seller_count":
                    seller_count,

                "positive_landed_price_count":
                    positive_price_count,

                "ebay_median_landed_price":
                    ebay_median
                    if ebay_median is not None
                    else "",

                "ebay_landed_price_stddev":
                    ebay_stddev
                    if ebay_stddev is not None
                    else "",

                "ebay_landed_price_cv":
                    ebay_cv
                    if ebay_cv is not None
                    else "",

                "ebay_landed_price_iqr":
                    ebay_iqr
                    if ebay_iqr is not None
                    else "",

                # SOURCE_DISAGREEMENT
                "tcgcsv_minus_ebay_median":
                    source_difference
                    if source_difference is not None
                    else "",

                "tcgcsv_vs_ebay_pct_difference":
                    source_pct_difference
                    if source_pct_difference is not None
                    else "",

                # MISSINGNESS / DATA-QUALITY STRUCTURE
                "missing_history":
                    str(
                        missing_history
                    ).lower(),

                "missing_current_price":
                    str(
                        missing_current
                    ).lower(),

                "missing_availability":
                    str(
                        missing_availability
                    ).lower(),

                "evidence_domains_present":
                    evidence_domains_present,

                # MODEL-DEPENDENT DIMENSIONS
                "statistical_influence_status":
                    "PENDING_MODEL_VARIANT_EXECUTION",

                "out_of_sample_error_contribution_status":
                    "PENDING_MODEL_VARIANT_EXECUTION",

                "model_stability_status":
                    "PENDING_MODEL_VARIANT_EXECUTION",

                "exclusion_sensitivity_status":
                    "PENDING_MODEL_VARIANT_EXECUTION",

                # GOVERNANCE
                "canonical_membership":
                    "true",

                "model_exclusion_authorized":
                    "false",

                "model_treatment_assigned":
                    "UNASSIGNED_PENDING_EMPIRICAL_MODEL_DIAGNOSTICS",
            }
        )

    if len(diagnostics) != 131:
        fail(
            "diagnostics ledger is not 131 rows"
        )

    # ========================================================================
    # Summary statistics — descriptive only
    # ========================================================================

    complete_three_domain = sum(
        1
        for row in diagnostics
        if row[
            "evidence_domains_present"
        ]
        == 3
    )

    two_domain = sum(
        1
        for row in diagnostics
        if row[
            "evidence_domains_present"
        ]
        == 2
    )

    one_domain = sum(
        1
        for row in diagnostics
        if row[
            "evidence_domains_present"
        ]
        == 1
    )

    zero_domain = sum(
        1
        for row in diagnostics
        if row[
            "evidence_domains_present"
        ]
        == 0
    )

    with_disagreement = sum(
        1
        for row in diagnostics
        if row[
            "tcgcsv_vs_ebay_pct_difference"
        ]
        != ""
    )

    # ========================================================================
    # Outputs
    # ========================================================================

    output_root = (
        args.output_root.resolve()
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    ledger_path = (
        output_root
        / "precollector_empirical_eligibility_diagnostics_v1.csv"
    )

    summary_path = (
        output_root
        / "precollector_empirical_eligibility_diagnostics_v1_summary.json"
    )

    manifest_path = (
        output_root
        / "precollector_empirical_eligibility_diagnostics_v1_manifest.json"
    )

    fields = list(
        diagnostics[0].keys()
    )

    write_csv(
        ledger_path,
        diagnostics,
        fields,
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_EMPIRICAL_ELIGIBILITY_DIAGNOSTICS_V1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "operating_date":
            operating_date.isoformat(),

        "canonical_product_count":
            131,

        "history_covered_products":
            115,

        "current_price_covered_products":
            121,

        "availability_covered_products":
            111,

        "all_three_evidence_domains_products":
            complete_three_domain,

        "two_evidence_domain_products":
            two_domain,

        "one_evidence_domain_products":
            one_domain,

        "zero_evidence_domain_products":
            zero_domain,

        "products_with_tcgcsv_ebay_price_comparison":
            with_disagreement,

        "arbitrary_age_cutoff_used":
            False,

        "arbitrary_history_cutoff_used":
            False,

        "arbitrary_listing_cutoff_used":
            False,

        "arbitrary_seller_cutoff_used":
            False,

        "model_exclusions_assigned":
            0,

        "model_treatments_assigned":
            0,

        "model_execution_authorized":
            False,

        "model_dependent_diagnostics_pending": [
            "STATISTICAL_INFLUENCE",
            "OUT_OF_SAMPLE_ERROR_CONTRIBUTION",
            "MODEL_STABILITY",
            "EXCLUSION_SENSITIVITY",
        ],

        "authorized_next_stage":
            "DESIGN_PRECOLLECTOR_MODEL_VARIANT_TOURNAMENT_AND_OOS_DIAGNOSTICS",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "manifest_id":
            "precollector_empirical_eligibility_diagnostics_v1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "canonical_identity_sha256":
            identity_sha,

        "universe_package_sha256":
            sha256_file(
                args.universe_package
            ),

        "history_package_sha256":
            sha256_file(
                args.history_package
            ),

        "current_package_sha256":
            sha256_file(
                args.current_package
            ),

        "availability_package_sha256":
            sha256_file(
                args.availability_package
            ),

        "members": [
            {
                "file_name":
                    ledger_path.name,

                "byte_length":
                    ledger_path.stat().st_size,

                "sha256":
                    sha256_file(
                        ledger_path
                    ),
            },
            {
                "file_name":
                    summary_path.name,

                "byte_length":
                    summary_path.stat().st_size,

                "sha256":
                    sha256_file(
                        summary_path
                    ),
            },
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
        "PASS_PRECOLLECTOR_EMPIRICAL_ELIGIBILITY_DIAGNOSTICS_V1"
    )

    print(
        "CANONICAL_PRODUCT_COUNT=131"
    )

    print(
        "HISTORY_COVERED_PRODUCTS=115"
    )

    print(
        "CURRENT_PRICE_COVERED_PRODUCTS=121"
    )

    print(
        "AVAILABILITY_COVERED_PRODUCTS=111"
    )

    print(
        "ALL_THREE_EVIDENCE_DOMAINS_PRODUCTS="
        f"{complete_three_domain}"
    )

    print(
        "TWO_EVIDENCE_DOMAIN_PRODUCTS="
        f"{two_domain}"
    )

    print(
        "ONE_EVIDENCE_DOMAIN_PRODUCTS="
        f"{one_domain}"
    )

    print(
        "ZERO_EVIDENCE_DOMAIN_PRODUCTS="
        f"{zero_domain}"
    )

    print(
        "PRODUCTS_WITH_SOURCE_DISAGREEMENT_MEASURE="
        f"{with_disagreement}"
    )

    print(
        "MODEL_EXCLUSIONS_ASSIGNED=0"
    )

    print(
        "MODEL_TREATMENTS_ASSIGNED=0"
    )

    print(
        "MODEL_EXECUTION_AUTHORIZED=FALSE"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())