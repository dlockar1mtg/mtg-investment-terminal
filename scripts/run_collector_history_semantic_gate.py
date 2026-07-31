from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "operations"
    / "collector_booster_history_certification"
    / "candidate_v1_0_0"
)

CERTIFICATION_PATH = (
    OUTPUT_ROOT
    / "collector_history_product_certification.csv"
)

MANIFEST_PATH = (
    OUTPUT_ROOT
    / "collector_history_certification_manifest.json"
)


def clean(value: object) -> str:
    return str(value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    rows = read_csv(CERTIFICATION_PATH)

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(MANIFEST_PATH)

    manifest = json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    failures: list[str] = []

    ids = [
        clean(row.get("investment_product_id"))
        for row in rows
    ]

    if len(rows) != 51:
        failures.append(
            f"UNEXPECTED_DISPLAY_UNIVERSE_SIZE:{len(rows)}"
        )

    if manifest.get(
        "production_collector_products"
    ) != len(rows):
        failures.append(
            "MANIFEST_PRODUCT_COUNT_MISMATCH"
        )

    if manifest.get(
        "model_collector_products"
    ) != len(rows):
        failures.append(
            "MODEL_PRODUCT_COUNT_MISMATCH"
        )

    if any(not value for value in ids):
        failures.append(
            "BLANK_INVESTMENT_PRODUCT_ID"
        )

    if len(ids) != len(set(ids)):
        failures.append(
            "DUPLICATE_INVESTMENT_PRODUCT_ID"
        )

    case_terms = (
        "master case",
        "box case",
        "display case",
        "collector booster case",
        "booster case",
        "case of",
    )

    for row in rows:
        investment_id = clean(
            row.get("investment_product_id")
        )

        name = clean(
            row.get("product_name")
        ).lower()

        status = clean(
            row.get("history_certification_status")
        )

        band = clean(
            row.get("history_quality_band")
        )

        forecast_allowed = clean(
            row.get("direct_forecast_allowed")
        ).lower()

        if any(term in name for term in case_terms):
            failures.append(
                "NON_DISPLAY_CONFIGURATION_PRESENT:"
                + investment_id
            )

        if (
            status in {
                "QUARANTINED",
                "HISTORY_ACCUMULATING",
            }
            and forecast_allowed == "true"
        ):
            failures.append(
                "BLOCKED_PRODUCT_FORECAST_ENABLED:"
                + investment_id
            )

        if (
            band in {
                "NONE",
                "VERY_LIMITED",
                "LIMITED",
            }
            and forecast_allowed == "true"
        ):
            failures.append(
                "INSUFFICIENT_HISTORY_FORECAST_ENABLED:"
                + investment_id
            )

        if (
            status in {
                "CERTIFIED",
                "CERTIFIED_LIMITED",
            }
            and forecast_allowed != "true"
        ):
            failures.append(
                "CERTIFIED_PRODUCT_FORECAST_BLOCKED:"
                + investment_id
            )

    star_trek = [
        row
        for row in rows
        if "star trek" in clean(
            row.get("product_name")
        ).lower()
    ]

    if len(star_trek) != 1:
        failures.append(
            "STAR_TREK_IDENTITY_COUNT_INVALID"
        )
    else:
        row = star_trek[0]

        if clean(
            row.get("history_certification_status")
        ) != "HISTORY_ACCUMULATING":
            failures.append(
                "STAR_TREK_STATUS_INVALID"
            )

        if clean(
            row.get("direct_forecast_allowed")
        ).lower() != "false":
            failures.append(
                "STAR_TREK_FORECAST_INCORRECTLY_ENABLED"
            )

    allowed_count = sum(
        clean(
            row.get("direct_forecast_allowed")
        ).lower() == "true"
        for row in rows
    )

    blocked_count = len(rows) - allowed_count

    if allowed_count != manifest.get(
        "forecast_allowed_count"
    ):
        failures.append(
            "FORECAST_ALLOWED_COUNT_MISMATCH"
        )

    if blocked_count != manifest.get(
        "forecast_blocked_count"
    ):
        failures.append(
            "FORECAST_BLOCKED_COUNT_MISMATCH"
        )

    if manifest.get(
        "purchase_recommendations_authorized"
    ) is not False:
        failures.append(
            "PURCHASE_RECOMMENDATIONS_INCORRECTLY_AUTHORIZED"
        )

    if failures:
        print("SEMANTIC CERTIFICATION: FAILED")

        for failure in failures:
            print(f" - {failure}")

        sys.exit(1)

    print("SEMANTIC CERTIFICATION: PASS")
    print(f"Products evaluated: {len(rows)}")
    print(f"Unique identities: {len(set(ids))}")
    print(f"Forecast eligible: {allowed_count}")
    print(f"Forecast blocked: {blocked_count}")
    print(
        "Anomaly products: "
        f"{manifest['anomaly_product_count']}"
    )
    print(
        "Purchase authorization: "
        f"{manifest['purchase_recommendations_authorized']}"
    )


if __name__ == "__main__":
    main()