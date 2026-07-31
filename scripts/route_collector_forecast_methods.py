from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_REGISTRY = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

DEFAULT_MODEL = (
    ROOT
    / "data"
    / "product_master"
    / "product_master_model_input.csv"
)

DEFAULT_HISTORY_CERTIFICATION = (
    ROOT
    / "data"
    / "operations"
    / "collector_booster_history_certification"
    / "candidate_v1_0_0"
    / "collector_history_product_certification.csv"
)

DEFAULT_POLICY = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "collector_forecast_method_router_v1.json"
)

DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "data"
    / "operations"
    / "collector_forecast_method_routing"
    / "candidate_v1_0_0"
)


OUTPUT_FIELDS = [
    "investment_product_id",
    "product_name",
    "product_lane",
    "identity_status",
    "current_price",
    "history_certification_status",
    "history_quality_band",
    "direct_history_method_allowed",
    "comparable_method_allowed",
    "forecast_output_allowed",
    "purchase_analysis_allowed",
    "purchase_recommendation_authorized",
    "forecast_method",
    "base_forecast_method",
    "override_applied",
    "override_reason_code",
    "override_version",
    "forecast_method_version",
    "method_reason",
    "comparable_group_required",
    "limitations",
    "standard_name",
    "standard_version",
]


DEFAULT_OVERRIDE = (
    ROOT
    / "data"
    / "governance"
    / "mtg"
    / "collector_comparables"
    / "collector_japanese_edition_hybrid_override_v1.json"
)


def clean(value: object) -> str:
    return str(value or "").strip()


def clean_upper(value: object) -> str:
    return clean(value).upper()


def parse_bool(value: object) -> bool:
    return clean(value).lower() in {
        "true",
        "1",
        "yes",
        "y",
    }


def parse_float(value: object) -> float | None:
    text = clean(value)

    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest().upper()


def index_unique(
    rows: list[dict[str, str]],
    key: str,
    label: str,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}

    for row in rows:
        value = clean(row.get(key))

        if not value:
            raise RuntimeError(
                f"{label} contains blank {key}."
            )

        if value in result:
            raise RuntimeError(
                f"{label} contains duplicate {key}: "
                f"{value}"
            )

        result[value] = row

    return result


def infer_identity_status(
    registry_row: dict[str, str],
) -> str:
    candidates = [
        registry_row.get("identity_status"),
        registry_row.get("approval_status"),
        registry_row.get("status"),
    ]

    for value in candidates:
        normalized = clean_upper(value)

        if normalized:
            return normalized

    return "VERIFIED"


def infer_current_price(
    model_row: dict[str, str],
    registry_row: dict[str, str],
) -> float | None:
    candidates = [
        model_row.get("current_price"),
        model_row.get("market_price"),
        registry_row.get("current_price"),
        registry_row.get("market_price"),
    ]

    for value in candidates:
        parsed = parse_float(value)

        if parsed is not None:
            return parsed

    return None


def route_product(
    *,
    investment_product_id: str,
    registry_row: dict[str, str],
    model_row: dict[str, str],
    history_row: dict[str, str] | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    product_name = clean(
        history_row.get("product_name")
        if history_row
        else registry_row.get("box_name")
    )

    if not product_name:
        product_name = clean(
            registry_row.get("approved_product_name")
        )

    identity_status = infer_identity_status(
        registry_row
    )

    current_price = infer_current_price(
        model_row,
        registry_row,
    )

    history_status = clean_upper(
        history_row.get(
            "history_certification_status"
        )
        if history_row
        else ""
    )

    quality_band = clean_upper(
        history_row.get(
            "history_quality_band"
        )
        if history_row
        else ""
    )

    valid_identity_statuses = {
        clean_upper(value)
        for value in policy[
            "identity_valid_statuses"
        ]
    }

    method_version = policy[
        "policy_version"
    ]

    standard_name = policy[
        "standard_name"
    ]

    standard_version = policy[
        "standard_version"
    ]

    purchase_authorized = bool(
        policy[
            "purchase_recommendation_authorized"
        ]
    )

    if identity_status not in valid_identity_statuses:
        method = policy[
            "fail_closed_rules"
        ]["identity_invalid_method"]

        return {
            "investment_product_id": investment_product_id,
            "product_name": product_name,
            "product_lane": policy["lane"],
            "identity_status": identity_status,
            "current_price": (
                ""
                if current_price is None
                else current_price
            ),
            "history_certification_status": history_status,
            "history_quality_band": quality_band,
            "direct_history_method_allowed": False,
            "comparable_method_allowed": False,
            "forecast_output_allowed": False,
            "purchase_analysis_allowed": False,
            "purchase_recommendation_authorized": purchase_authorized,
            "forecast_method": method,
            "forecast_method_version": method_version,
            "method_reason": (
                "Identity status is not approved for "
                "forecast publication."
            ),
            "comparable_group_required": False,
            "limitations": "Identity must be resolved.",
            "standard_name": standard_name,
            "standard_version": standard_version,
        }

    if current_price is None or current_price <= 0:
        method = policy[
            "fail_closed_rules"
        ][
            "missing_or_nonpositive_current_price_method"
        ]

        return {
            "investment_product_id": investment_product_id,
            "product_name": product_name,
            "product_lane": policy["lane"],
            "identity_status": identity_status,
            "current_price": "",
            "history_certification_status": history_status,
            "history_quality_band": quality_band,
            "direct_history_method_allowed": False,
            "comparable_method_allowed": False,
            "forecast_output_allowed": False,
            "purchase_analysis_allowed": False,
            "purchase_recommendation_authorized": purchase_authorized,
            "forecast_method": method,
            "forecast_method_version": method_version,
            "method_reason": (
                "No positive current executable price "
                "is available."
            ),
            "comparable_group_required": False,
            "limitations": (
                "Current price evidence is missing "
                "or invalid."
            ),
            "standard_name": standard_name,
            "standard_version": standard_version,
        }

    if not history_row:
        method = policy[
            "fail_closed_rules"
        ][
            "missing_history_certification_method"
        ]

        return {
            "investment_product_id": investment_product_id,
            "product_name": product_name,
            "product_lane": policy["lane"],
            "identity_status": identity_status,
            "current_price": current_price,
            "history_certification_status": "",
            "history_quality_band": "",
            "direct_history_method_allowed": False,
            "comparable_method_allowed": False,
            "forecast_output_allowed": False,
            "purchase_analysis_allowed": False,
            "purchase_recommendation_authorized": purchase_authorized,
            "forecast_method": method,
            "forecast_method_version": method_version,
            "method_reason": (
                "No governed history certification "
                "record is available."
            ),
            "comparable_group_required": False,
            "limitations": (
                "History certification must be "
                "completed."
            ),
            "standard_name": standard_name,
            "standard_version": standard_version,
        }

    rule = policy[
        "routing_rules"
    ].get(history_status)

    if rule is None:
        method = policy[
            "fail_closed_rules"
        ][
            "unknown_history_status_method"
        ]

        return {
            "investment_product_id": investment_product_id,
            "product_name": product_name,
            "product_lane": policy["lane"],
            "identity_status": identity_status,
            "current_price": current_price,
            "history_certification_status": history_status,
            "history_quality_band": quality_band,
            "direct_history_method_allowed": False,
            "comparable_method_allowed": False,
            "forecast_output_allowed": False,
            "purchase_analysis_allowed": False,
            "purchase_recommendation_authorized": purchase_authorized,
            "forecast_method": method,
            "forecast_method_version": method_version,
            "method_reason": (
                "History certification status is "
                "not governed by the router policy."
            ),
            "comparable_group_required": False,
            "limitations": (
                "Router policy must explicitly "
                "govern this state."
            ),
            "standard_name": standard_name,
            "standard_version": standard_version,
        }

    method = clean(
        rule["forecast_method"]
    )

    comparable_required = method in {
        "COMPARABLE_PRODUCT_ADJUSTED",
        "FUNDAMENTAL_COMPARABLE_HYBRID",
    }

    if method == "DIRECT_HISTORY_CALIBRATED":
        reason = (
            "Strong governed direct history is "
            "eligible for calibrated forecasting."
        )
        limitations = (
            "Comparable evidence may be used as "
            "secondary validation."
        )
    elif method == "DIRECT_HISTORY_LIMITED":
        reason = (
            "Moderate governed history is eligible "
            "for limited direct forecasting."
        )
        limitations = (
            "Confidence must be reduced and "
            "uncertainty widened."
        )
    elif history_status == "QUARANTINED":
        reason = (
            "The direct historical series is "
            "quarantined; comparable forecasting "
            "is required."
        )
        limitations = (
            "Direct historical returns must not "
            "be used until repaired and recertified."
        )
    else:
        reason = (
            "Direct history is still accumulating; "
            "comparable forecasting is required."
        )
        limitations = (
            "Comparable evidence must disclose "
            "selection basis and uncertainty."
        )

    return {
        "investment_product_id": investment_product_id,
        "product_name": product_name,
        "product_lane": policy["lane"],
        "identity_status": identity_status,
        "current_price": current_price,
        "history_certification_status": history_status,
        "history_quality_band": quality_band,
        "direct_history_method_allowed": bool(
            rule[
                "direct_history_method_allowed"
            ]
        ),
        "comparable_method_allowed": bool(
            rule[
                "comparable_method_allowed"
            ]
        ),
        "forecast_output_allowed": bool(
            rule[
                "forecast_output_allowed"
            ]
        ),
        "purchase_analysis_allowed": bool(
            rule[
                "purchase_analysis_allowed"
            ]
        ),
        "purchase_recommendation_authorized": purchase_authorized,
        "forecast_method": method,
        "forecast_method_version": method_version,
        "method_reason": reason,
        "comparable_group_required": comparable_required,
        "limitations": limitations,
        "standard_name": standard_name,
        "standard_version": standard_version,
    }


def run(
    *,
    registry_path: Path,
    model_path: Path,
    history_certification_path: Path,
    policy_path: Path,
    override_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    policy = json.loads(
        policy_path.read_text(
            encoding="utf-8-sig"
        )
    )

    override: dict[str, Any] | None = None

    if override_path.exists():
        override = json.loads(
            override_path.read_text(
                encoding="utf-8-sig"
            )
        )

        required_override_fields = {
            "investment_product_id",
            "previous_method",
            "approved_method",
            "reason_code",
            "override_version",
            "projection_authorized",
            "purchase_recommendation_authorized",
        }

        missing_override_fields = (
            required_override_fields
            - set(override)
        )

        if missing_override_fields:
            raise RuntimeError(
                "Override missing required fields: "
                + ", ".join(
                    sorted(
                        missing_override_fields
                    )
                )
            )

        if bool(
            override[
                "projection_authorized"
            ]
        ):
            raise RuntimeError(
                "Override cannot authorize projections."
            )

        if bool(
            override[
                "purchase_recommendation_authorized"
            ]
        ):
            raise RuntimeError(
                "Override cannot authorize purchases."
            )

    registry_rows = read_csv(
        registry_path
    )

    model_rows = read_csv(
        model_path
    )

    history_rows = read_csv(
        history_certification_path
    )

    registry_index = index_unique(
        registry_rows,
        "investment_product_id",
        "registry",
    )

    model_index = index_unique(
        model_rows,
        "investment_product_id",
        "model",
    )

    history_index = index_unique(
        history_rows,
        "investment_product_id",
        "history certification",
    )

    governed_ids = sorted(
        history_index
    )

    routed_rows: list[dict[str, Any]] = []

    for investment_product_id in governed_ids:
        if investment_product_id not in registry_index:
            raise RuntimeError(
                "History-certified identity missing "
                "from registry: "
                + investment_product_id
            )

        if investment_product_id not in model_index:
            raise RuntimeError(
                "History-certified identity missing "
                "from model: "
                + investment_product_id
            )

        routed_rows.append(
            route_product(
                investment_product_id=(
                    investment_product_id
                ),
                registry_row=registry_index[
                    investment_product_id
                ],
                model_row=model_index[
                    investment_product_id
                ],
                history_row=history_index[
                    investment_product_id
                ],
                policy=policy,
            )
        )

    override_applied_count = 0

    for row in routed_rows:
        row[
            "base_forecast_method"
        ] = clean(
            row.get(
                "forecast_method"
            )
        )

        row[
            "override_applied"
        ] = False

        row[
            "override_reason_code"
        ] = ""

        row[
            "override_version"
        ] = ""

        if (
            override is None
            or clean(
                row.get(
                    "investment_product_id"
                )
            )
            != clean(
                override.get(
                    "investment_product_id"
                )
            )
        ):
            continue

        expected_previous_method = clean(
            override.get(
                "previous_method"
            )
        )

        if (
            row[
                "base_forecast_method"
            ]
            != expected_previous_method
        ):
            raise RuntimeError(
                "Override previous method mismatch "
                f"for "
                f"{row['investment_product_id']}: "
                f"expected "
                f"{expected_previous_method}, "
                f"found "
                f"{row['base_forecast_method']}."
            )

        approved_method = clean(
            override.get(
                "approved_method"
            )
        )

        if not approved_method:
            raise RuntimeError(
                "Override approved method is blank."
            )

        row[
            "forecast_method"
        ] = approved_method

        row[
            "override_applied"
        ] = True

        row[
            "override_reason_code"
        ] = clean(
            override.get(
                "reason_code"
            )
        )

        row[
            "override_version"
        ] = clean(
            override.get(
                "override_version"
            )
        )

        row[
            "comparable_group_required"
        ] = approved_method in {
            "COMPARABLE_PRODUCT_ADJUSTED",
            "FUNDAMENTAL_COMPARABLE_HYBRID",
        }

        row[
            "method_reason"
        ] = (
            clean(
                row.get(
                    "method_reason"
                )
            )
            + " Governed override applied: "
            + row[
                "override_reason_code"
            ]
            + "."
        )

        row[
            "limitations"
        ] = (
            clean(
                row.get(
                    "limitations"
                )
            )
            + " Hybrid method requires wider "
            + "uncertainty due to insufficient "
            + "exact semantic comparables."
        )

        override_applied_count += 1

    if (
        override is not None
        and override_applied_count != 1
    ):
        raise RuntimeError(
            "Expected exactly one governed override "
            f"application, found "
            f"{override_applied_count}."
        )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_root
        / "collector_forecast_method_routes.csv"
    )

    deferred_path = (
        output_root
        / "collector_forecast_method_deferred.csv"
    )

    comparable_path = (
        output_root
        / "collector_comparable_method_required.csv"
    )

    write_csv(
        output_path,
        routed_rows,
        OUTPUT_FIELDS,
    )

    deferred_rows = [
        row
        for row in routed_rows
        if clean(row["forecast_method"]).startswith(
            "DEFERRED_"
        )
    ]

    comparable_rows = [
        row
        for row in routed_rows
        if parse_bool(
            row["comparable_group_required"]
        )
    ]

    write_csv(
        deferred_path,
        deferred_rows,
        OUTPUT_FIELDS,
    )

    write_csv(
        comparable_path,
        comparable_rows,
        OUTPUT_FIELDS,
    )

    method_counts = Counter(
        clean(row["forecast_method"])
        for row in routed_rows
    )

    history_status_counts = Counter(
        clean(
            row[
                "history_certification_status"
            ]
        )
        for row in routed_rows
    )

    manifest = {
        "status": (
            "PASS"
            if len(routed_rows) == len(governed_ids)
            else "FAILED"
        ),
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "policy_name": policy[
            "policy_name"
        ],
        "policy_version": policy[
            "policy_version"
        ],
        "standard_name": policy[
            "standard_name"
        ],
        "standard_version": policy[
            "standard_version"
        ],
        "lane": policy["lane"],
        "governed_product_count": len(
            governed_ids
        ),
        "routed_product_count": len(
            routed_rows
        ),
        "override_applied_count": (
            override_applied_count
        ),
        "method_counts": dict(
            sorted(method_counts.items())
        ),
        "history_status_counts": dict(
            sorted(
                history_status_counts.items()
            )
        ),
        "comparable_group_required_count": len(
            comparable_rows
        ),
        "deferred_product_count": len(
            deferred_rows
        ),
        "purchase_recommendations_authorized": False,
        "inputs": {
            "registry_path": str(
                registry_path.resolve()
            ),
            "registry_sha256": sha256(
                registry_path
            ),
            "model_path": str(
                model_path.resolve()
            ),
            "model_sha256": sha256(
                model_path
            ),
            "history_certification_path": str(
                history_certification_path.resolve()
            ),
            "history_certification_sha256": sha256(
                history_certification_path
            ),
            "policy_path": str(
                policy_path.resolve()
            ),
            "policy_sha256": sha256(
                policy_path
            ),
            "override_path": (
                str(
                    override_path.resolve()
                )
                if override_path.exists()
                else ""
            ),
            "override_sha256": (
                sha256(
                    override_path
                )
                if override_path.exists()
                else ""
            ),
        },
        "outputs": {
            "routes": str(
                output_path.resolve()
            ),
            "deferred": str(
                deferred_path.resolve()
            ),
            "comparable_required": str(
                comparable_path.resolve()
            ),
        },
    }

    manifest_path = (
        output_root
        / "collector_forecast_method_router_manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Route every governed Collector "
            "Booster product to an approved "
            "forecast method."
        )
    )

    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
    )

    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
    )

    parser.add_argument(
        "--history-certification",
        type=Path,
        default=DEFAULT_HISTORY_CERTIFICATION,
    )

    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
    )

    parser.add_argument(
        "--override",
        type=Path,
        default=DEFAULT_OVERRIDE,
    )


    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    manifest = run(
        registry_path=args.registry,
        model_path=args.model,
        history_certification_path=(
            args.history_certification
        ),
        policy_path=args.policy,
        override_path=args.override,
        output_root=args.output_root,
    )

    print(
        "COLLECTOR FORECAST METHOD ROUTER COMPLETE"
    )
    print(
        json.dumps(
            manifest,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()