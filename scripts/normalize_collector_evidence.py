from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_MAP = (
    ROOT
    / "config"
    / "mtg"
    / "evidence"
    / "collector_evidence_source_map_v1.json"
)

DEFAULT_POLICY = (
    ROOT
    / "config"
    / "mtg"
    / "evidence"
    / "collector_evidence_normalization_v1.json"
)

DEFAULT_ROUTER = (
    ROOT
    / "data"
    / "operations"
    / "collector_forecast_method_routing"
    / "candidate_v1_0_0"
    / "collector_forecast_method_routes.csv"
)

DEFAULT_REGISTRY = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

DEFAULT_HISTORY = (
    ROOT
    / "data"
    / "operations"
    / "collector_booster_history_certification"
    / "candidate_v1_0_0"
    / "collector_history_product_certification.csv"
)

DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "operations"
    / "collector_evidence_normalization"
    / "candidate_v1_0_0"
)


OUTPUT_FIELDS = [
    "investment_product_id",
    "product_name",
    "product_lane",
    "identity_status",
    "release_date",
    "release_date_method",
    "release_date_confidence_class",
    "product_configuration",
    "forecast_method",
    "current_price",
    "supply_score",
    "scarcity_signal_score",
    "inventory_signal_score",
    "inventory_risk_proxy",
    "supply_dump_risk",
    "demand_score",
    "real_demand_score",
    "sales_velocity_score",
    "demand_signal_confidence",
    "expected_value_support_score",
    "liquidity_score",
    "liquidity_proxy_score",
    "liquidity_risk",
    "annualized_volatility",
    "return_365d",
    "print_run_quantity",
    "marketplace_listing_count",
    "transaction_count",
    "supply_evidence_type",
    "demand_evidence_type",
    "liquidity_evidence_type",
    "supply_component_count",
    "demand_component_count",
    "liquidity_component_count",
    "supply_confidence_score",
    "demand_confidence_score",
    "liquidity_confidence_score",
    "supply_confidence_class",
    "demand_confidence_class",
    "liquidity_confidence_class",
    "release_era_class",
    "lifecycle_stage",
    "price_band_class",
    "supply_profile_class",
    "liquidity_class",
    "reprint_exposure_class",
    "franchise_class",
    "premium_contents_class",
    "comparable_dimension_count",
    "supply_evidence_ready",
    "demand_evidence_ready",
    "liquidity_evidence_ready",
    "comparable_evidence_ready",
    "missing_evidence_flags",
    "proxy_methods_used",
    "limitations",
    "evidence_source_path",
    "evidence_observed_at",
    "normalization_policy_version",
    "purchase_recommendation_authorized",
]


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_float(value: object) -> float | None:
    text = clean(value).replace(",", "")

    if not text:
        return None

    try:
        result = float(text)
    except ValueError:
        return None

    if not math.isfinite(result):
        return None

    return result


def parse_date(value: object) -> datetime | None:
    text = clean(value)

    if not text:
        return None

    candidates = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    normalized = text.replace("Z", "")

    for pattern in candidates:
        try:
            return datetime.strptime(
                normalized[:26],
                pattern,
            )
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(
            normalized
        )
    except ValueError:
        return None


def derive_release_date(
    *,
    explicit_release_date: object,
    latest_observation_date: object,
    months_since_release: float | None,
) -> tuple[str, str]:
    explicit = parse_date(
        explicit_release_date
    )

    if explicit is not None:
        return (
            explicit.date().isoformat(),
            "DIRECT_OR_SOURCE_RELEASE_DATE",
        )

    latest = parse_date(
        latest_observation_date
    )

    if (
        latest is not None
        and months_since_release is not None
        and months_since_release >= 0
    ):
        estimated = latest - relativedelta(
            months=int(
                round(months_since_release)
            )
        )

        return (
            estimated.date().isoformat(),
            "DERIVED_FROM_LATEST_OBSERVATION_AND_MONTHS_SINCE_RELEASE",
        )

    return "", "UNKNOWN"


def parse_year(value: object) -> int | None:
    text = clean(value)

    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])

    return None


def normalize_score(value: object) -> float | None:
    parsed = parse_float(value)

    if parsed is None:
        return None

    if 0 <= parsed <= 1:
        parsed *= 100

    if not 0 <= parsed <= 100:
        return None

    return round(parsed, 6)


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
        )
        writer.writeheader()
        writer.writerows(rows)


def index_unique(
    rows: list[dict[str, str]],
    key: str,
    label: str,
) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}

    for row in rows:
        identity = clean(row.get(key))

        if not identity:
            raise RuntimeError(
                f"{label} contains blank {key}."
            )

        if identity in output:
            raise RuntimeError(
                f"{label} contains duplicate identity: "
                f"{identity}"
            )

        output[identity] = row

    return output


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest().upper()


def confidence_class(
    score: float,
    policy: dict[str, Any],
) -> str:
    classes = policy["confidence_classes"]

    for name in [
        "HIGH",
        "MODERATE",
        "LOW",
        "INSUFFICIENT",
    ]:
        if score >= float(
            classes[name]["minimum"]
        ):
            return name

    return "INSUFFICIENT"


def group_confidence(
    values: list[float | None],
) -> tuple[int, float]:
    present = [
        value
        for value in values
        if value is not None
    ]

    if not present:
        return 0, 0.0

    coverage = len(present) / len(values)
    centrality = mean(present) / 100

    score = 100 * (
        0.65 * coverage
        + 0.35 * centrality
    )

    return len(present), round(
        max(0, min(100, score)),
        6,
    )


def price_band(
    price: float | None,
    policy: dict[str, Any],
) -> str:
    if price is None:
        return "UNKNOWN"

    for band in policy[
        "comparable_classes"
    ]["price_bands"]:
        maximum = band["maximum"]

        if maximum is None or price <= float(maximum):
            return clean(band["class"])

    return "UNKNOWN"


def threshold_class(
    value: float | None,
    thresholds: dict[str, float],
) -> str:
    if value is None:
        return "UNKNOWN"

    ordered = sorted(
        thresholds.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    for label, minimum in ordered:
        if value >= float(minimum):
            return label

    return "UNKNOWN"


def release_era(
    release_year: int | None,
    policy: dict[str, Any],
) -> str:
    if release_year is None:
        return "UNKNOWN"

    thresholds = policy[
        "comparable_classes"
    ]["release_era"]

    if release_year >= thresholds["CURRENT"]:
        return "CURRENT"

    if release_year >= thresholds["RECENT"]:
        return "RECENT"

    if release_year >= thresholds["EARLY_COLLECTOR"]:
        return "EARLY_COLLECTOR"

    return "PRE_COLLECTOR_OR_UNKNOWN"


def lifecycle_stage(
    release_year: int | None,
    months_since_release: float | None = None,
) -> str:
    if months_since_release is not None:
        if months_since_release <= 0:
            return "PRERELEASE_OR_LAUNCH"

        if months_since_release <= 12:
            return "EARLY_LIFECYCLE"

        if months_since_release <= 36:
            return "MID_LIFECYCLE"

        return "MATURE"

    if release_year is None:
        return "UNKNOWN"

    age = 2026 - release_year

    if age <= 0:
        return "PRERELEASE_OR_LAUNCH"

    if age == 1:
        return "EARLY_LIFECYCLE"

    if age <= 3:
        return "MID_LIFECYCLE"

    return "MATURE"


def first_value(
    rows: list[dict[str, str]],
    names: list[str],
) -> str:
    for row in rows:
        for name in names:
            value = clean(row.get(name))

            if value:
                return value

    return ""


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source-map",
        type=Path,
        default=DEFAULT_SOURCE_MAP,
    )

    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
    )

    parser.add_argument(
        "--router",
        type=Path,
        default=DEFAULT_ROUTER,
    )

    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
    )

    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    source_map = json.loads(
        args.source_map.read_text(
            encoding="utf-8-sig"
        )
    )

    policy = json.loads(
        args.policy.read_text(
            encoding="utf-8-sig"
        )
    )

    primary_path = (
        ROOT
        / source_map["primary_source"]["path"]
    )

    primary_rows = read_csv(primary_path)
    router_rows = read_csv(args.router)
    registry_rows = read_csv(args.registry)
    history_rows = read_csv(args.history)

    primary = index_unique(
        primary_rows,
        "investment_product_id",
        "primary evidence source",
    )

    router = index_unique(
        router_rows,
        "investment_product_id",
        "router",
    )

    registry = index_unique(
        registry_rows,
        "investment_product_id",
        "registry",
    )

    history = index_unique(
        history_rows,
        "investment_product_id",
        "history",
    )

    thresholds = policy[
        "readiness_thresholds"
    ]

    normalized_rows: list[dict[str, Any]] = []

    for identity in sorted(router):
        route = router[identity]
        source = primary.get(identity)
        registry_row = registry.get(identity, {})
        history_row = history.get(identity, {})

        if source is None:
            source = {}


        raw_price = parse_float(
            source.get("current_price")
        )

        supply_values = [
            normalize_score(
                source.get("supply_score")
            ),
            normalize_score(
                source.get("scarcity_signal_score")
            ),
            normalize_score(
                source.get("inventory_signal_score")
            ),
        ]

        demand_values = [
            normalize_score(
                source.get("demand_score")
            ),
            normalize_score(
                source.get("real_demand_score")
            ),
            normalize_score(
                source.get("sales_velocity_score")
            ),
        ]

        liquidity_values = [
            normalize_score(
                source.get("liquidity_score")
            ),
            normalize_score(
                source.get("liquidity_proxy_score")
            ),
        ]

        supply_count, supply_confidence = (
            group_confidence(supply_values)
        )

        demand_count, demand_confidence = (
            group_confidence(demand_values)
        )

        liquidity_count, liquidity_confidence = (
            group_confidence(liquidity_values)
        )

        explicit_release_date = first_value(
            [source, registry_row, history_row],
            [
                "release_date",
                "releaseDate",
                "released_at",
            ],
        )

        months_since_release = parse_float(
            source.get("months_since_release")
        )

        latest_observation_date = first_value(
            [source, history_row],
            [
                "latest_observation_date",
                "latest_snapshot_date",
            ],
        )

        (
            release_date,
            release_date_method,
        ) = derive_release_date(
            explicit_release_date=(
                explicit_release_date
            ),
            latest_observation_date=(
                latest_observation_date
            ),
            months_since_release=(
                months_since_release
            ),
        )

        release_year = parse_year(
            release_date
        )

        release_date_confidence_class = (
            "HIGH"
            if release_date_method
            == "DIRECT_OR_SOURCE_RELEASE_DATE"
            else "MODERATE"
            if release_date_method.startswith(
                "DERIVED_"
            )
            else "INSUFFICIENT"
        )

        product_configuration = first_value(
            [source, registry_row],
            [
                "investment_product_type",
                "product_configuration",
                "product_type",
            ],
        )

        if not product_configuration:
            product_configuration = (
                "COLLECTOR_BOOSTER_DISPLAY"
            )

        supply_class = threshold_class(
            supply_values[0],
            policy[
                "comparable_classes"
            ]["supply_classes"],
        )

        liquidity_class = threshold_class(
            liquidity_values[0],
            policy[
                "comparable_classes"
            ]["liquidity_classes"],
        )

        comparable_dimensions = {
            "release_era_class": release_era(
                release_year,
                policy,
            ),
            "lifecycle_stage": lifecycle_stage(
                release_year,
                months_since_release,
            ),
            "price_band_class": price_band(
                raw_price,
                policy,
            ),
            "supply_profile_class": supply_class,
            "liquidity_class": liquidity_class,
            "reprint_exposure_class": "UNKNOWN",
            "franchise_class": "UNKNOWN",
            "premium_contents_class": "UNKNOWN",
        }

        comparable_dimension_count = sum(
            clean(value) != "UNKNOWN"
            for value in comparable_dimensions.values()
        )

        supply_ready = (
            supply_count
            >= thresholds[
                "minimum_supply_components"
            ]
            and supply_confidence
            >= thresholds[
                "minimum_group_confidence_score"
            ]
        )

        demand_ready = (
            demand_count
            >= thresholds[
                "minimum_demand_components"
            ]
            and demand_confidence
            >= thresholds[
                "minimum_group_confidence_score"
            ]
        )

        liquidity_ready = (
            liquidity_count
            >= thresholds[
                "minimum_liquidity_components"
            ]
            and liquidity_confidence
            >= thresholds[
                "minimum_group_confidence_score"
            ]
        )

        comparable_ready = (
            supply_ready
            and demand_ready
            and liquidity_ready
            and comparable_dimension_count
            >= thresholds[
                "minimum_comparable_dimensions"
            ]
        )

        missing_flags: list[str] = []

        if not source:
            missing_flags.append(
                "PRIMARY_EVIDENCE_ROW_MISSING"
            )

        if not supply_ready:
            missing_flags.append(
                "SUPPLY_EVIDENCE_NOT_READY"
            )

        if not demand_ready:
            missing_flags.append(
                "DEMAND_EVIDENCE_NOT_READY"
            )

        if not liquidity_ready:
            missing_flags.append(
                "LIQUIDITY_EVIDENCE_NOT_READY"
            )

        if comparable_dimension_count < thresholds[
            "minimum_comparable_dimensions"
        ]:
            missing_flags.append(
                "COMPARABLE_DIMENSIONS_INSUFFICIENT"
            )

        limitations = [
            "Supply, demand, and liquidity values are governed proxies.",
            "Exact print-run quantity is unknown.",
            "Direct listing and transaction counts are not yet governed.",
        ]

        normalized_rows.append({
            "investment_product_id": identity,
            "product_name": clean(
                route.get("product_name")
            ),
            "product_lane": "COLLECTOR_BOOSTER",
            "identity_status": clean(
                route.get("identity_status")
            ),
            "release_date": release_date,
            "release_date_method": release_date_method,
            "release_date_confidence_class": (
                release_date_confidence_class
            ),
            "product_configuration": product_configuration,
            "forecast_method": clean(
                route.get("forecast_method")
            ),
            "current_price": (
                ""
                if raw_price is None
                else raw_price
            ),
            "supply_score": supply_values[0] or "",
            "scarcity_signal_score": supply_values[1] or "",
            "inventory_signal_score": supply_values[2] or "",
            "inventory_risk_proxy": (
                normalize_score(
                    source.get(
                        "inventory_risk_proxy"
                    )
                )
                or ""
            ),
            "supply_dump_risk": (
                normalize_score(
                    source.get(
                        "supply_dump_risk"
                    )
                )
                or ""
            ),
            "demand_score": demand_values[0] or "",
            "real_demand_score": demand_values[1] or "",
            "sales_velocity_score": demand_values[2] or "",
            "demand_signal_confidence": (
                normalize_score(
                    source.get(
                        "demand_signal_confidence"
                    )
                )
                or ""
            ),
            "expected_value_support_score": (
                parse_float(
                    source.get("mc_expected_value")
                )
                or ""
            ),
            "liquidity_score": liquidity_values[0] or "",
            "liquidity_proxy_score": liquidity_values[1] or "",
            "liquidity_risk": (
                normalize_score(
                    source.get("liquidity_risk")
                )
                or ""
            ),
            "annualized_volatility": (
                parse_float(
                    source.get(
                        "annualized_volatility"
                    )
                )
                or ""
            ),
            "return_365d": (
                parse_float(
                    source.get("return_365d")
                )
                or ""
            ),
            "print_run_quantity": "",
            "marketplace_listing_count": "",
            "transaction_count": "",
            "supply_evidence_type": "MARKET_PROXY",
            "demand_evidence_type": "MARKET_PROXY",
            "liquidity_evidence_type": "MARKET_PROXY",
            "supply_component_count": supply_count,
            "demand_component_count": demand_count,
            "liquidity_component_count": liquidity_count,
            "supply_confidence_score": supply_confidence,
            "demand_confidence_score": demand_confidence,
            "liquidity_confidence_score": liquidity_confidence,
            "supply_confidence_class": confidence_class(
                supply_confidence,
                policy,
            ),
            "demand_confidence_class": confidence_class(
                demand_confidence,
                policy,
            ),
            "liquidity_confidence_class": confidence_class(
                liquidity_confidence,
                policy,
            ),
            **comparable_dimensions,
            "comparable_dimension_count": comparable_dimension_count,
            "supply_evidence_ready": supply_ready,
            "demand_evidence_ready": demand_ready,
            "liquidity_evidence_ready": liquidity_ready,
            "comparable_evidence_ready": comparable_ready,
            "missing_evidence_flags": "|".join(
                missing_flags
            ),
            "proxy_methods_used": (
                "supply_score|scarcity_signal_score|"
                "inventory_signal_score|demand_score|"
                "real_demand_score|sales_velocity_score|"
                "liquidity_score|liquidity_proxy_score"
            ),
            "limitations": " ".join(limitations),
            "evidence_source_path": source_map[
                "primary_source"
            ]["path"],
            "evidence_observed_at": "2026-07-31",
            "normalization_policy_version": policy[
                "policy_version"
            ],
            "purchase_recommendation_authorized": False,
        })

    args.output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    evidence_path = (
        args.output_root
        / "collector_normalized_evidence.csv"
    )

    ready_path = (
        args.output_root
        / "collector_comparable_evidence_ready.csv"
    )

    review_path = (
        args.output_root
        / "collector_evidence_review_required.csv"
    )

    write_csv(
        evidence_path,
        normalized_rows,
        OUTPUT_FIELDS,
    )

    ready_rows = [
        row
        for row in normalized_rows
        if row["comparable_evidence_ready"]
    ]

    review_rows = [
        row
        for row in normalized_rows
        if not row["comparable_evidence_ready"]
    ]

    write_csv(
        ready_path,
        ready_rows,
        OUTPUT_FIELDS,
    )

    write_csv(
        review_path,
        review_rows,
        OUTPUT_FIELDS,
    )

    status_counts = Counter(
        "READY"
        if row["comparable_evidence_ready"]
        else "REVIEW_REQUIRED"
        for row in normalized_rows
    )

    manifest = {
        "status": (
            "PASS"
            if len(normalized_rows) == 51
            else "FAILED"
        ),
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "product_count": len(normalized_rows),
        "comparable_evidence_ready_count": len(
            ready_rows
        ),
        "review_required_count": len(
            review_rows
        ),
        "readiness_counts": dict(
            status_counts
        ),
        "purchase_recommendations_authorized": False,
        "inputs": {
            "primary_source": str(
                primary_path.resolve()
            ),
            "primary_source_sha256": sha256(
                primary_path
            ),
            "router_sha256": sha256(
                args.router
            ),
            "source_map_sha256": sha256(
                args.source_map
            ),
            "policy_sha256": sha256(
                args.policy
            ),
        },
        "outputs": {
            "normalized_evidence": str(
                evidence_path.resolve()
            ),
            "ready": str(
                ready_path.resolve()
            ),
            "review_required": str(
                review_path.resolve()
            ),
        },
        "limitations": [
            "No exact print-run quantities are asserted.",
            "No direct listing counts are asserted.",
            "No direct transaction counts are asserted.",
            "Readiness authorizes comparable selection only.",
            "Readiness does not authorize projections or purchases."
        ],
    }

    (
        args.output_root
        / "collector_evidence_normalization_manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "COLLECTOR EVIDENCE NORMALIZATION COMPLETE"
    )
    print(
        json.dumps(
            manifest,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()