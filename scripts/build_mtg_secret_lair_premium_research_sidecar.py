from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT
    / "docs"
    / "phase_8"
    / "secret_lair"
    / "secret_lair_v1_purchase_analysis.csv"
)

OUTPUT_DIR = (
    ROOT
    / "docs"
    / "phase_9"
    / "uip_export"
    / "premium_research"
)

OUTPUT = (
    OUTPUT_DIR
    / "mtg_secret_lair_premium_research.csv"
)

SUMMARY = (
    OUTPUT_DIR
    / "mtg_secret_lair_premium_research_summary.json"
)

EXPECTED_SOURCE_SHA256 = (
    "eb5efced959116eb7b174d4aff27c06d"
    "321e774eda39b3f8572d958499441cdb"
)

EXPECTED_SOURCE_ROWS = 787
EXPECTED_SOURCE_FIELDS = 58

IDENTITY_FIELDS = [
    "mtg_asset_id",
    "secret_lair_id",
    "product_name",
]

AUTHORIZED_SOURCE_FIELDS = [
    "current_tcg_market_price_usd",
    "certified_1y_point_forecast_usd",
    "certified_1y_point_return",

    "y1_q10_break_even_entry_price_usd",
    "current_price_margin_to_q10_break_even",
    "current_price_vs_q10_break_even_state",

    "y1_probability_of_loss",
    "y1_probability_of_positive_return",
    "y1_downside_tail_mean_total_return",
    "y1_upside_tail_mean_total_return",

    "y1_q10_terminal_value_usd",
    "y1_q50_terminal_value_usd",
    "y1_q90_terminal_value_usd",

    "y3_median_total_return_scenario",
    "y3_probability_of_loss_scenario",
    "y3_q10_terminal_value_scenario_usd",
    "y3_q50_terminal_value_scenario_usd",
    "y3_q90_terminal_value_scenario_usd",

    "y5_median_total_return_scenario",
    "y5_probability_of_loss_scenario",
    "y5_q10_terminal_value_scenario_usd",
    "y5_q50_terminal_value_scenario_usd",
    "y5_q90_terminal_value_scenario_usd",

    "own_history_evidence_class",
    "history_span_days",
    "historical_observation_count",
    "exact_structural_comparable_support",
    "exact_structural_comparable_product_count",
    "global_comparable_product_count",
    "exact_structural_comparable_event_count",
    "global_comparable_event_count",
]

LINEAGE_FIELDS = [
    "source_authority_path",
    "source_authority_sha256",
]

OUTPUT_FIELDS = (
    IDENTITY_FIELDS
    + AUTHORIZED_SOURCE_FIELDS
    + LINEAGE_FIELDS
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        fields = list(reader.fieldnames or [])
        rows = list(reader)

    return rows, fields


def strict_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    normalized = str(
        "" if value is None else value
    ).strip().lower()

    if normalized in {
        "",
        "false",
        "0",
        "no",
        "n",
    }:
        return False

    if normalized in {
        "true",
        "1",
        "yes",
        "y",
    }:
        return True

    raise RuntimeError(
        "Unsupported automatic_purchase_execution value: "
        f"{value!r}"
    )


def build() -> dict[str, Any]:
    source_sha = sha256(SOURCE)

    if source_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            "Source SHA-256 does not match the certified authority."
        )

    rows, source_fields = read_csv(SOURCE)

    if len(rows) != EXPECTED_SOURCE_ROWS:
        raise RuntimeError(
            "Source must contain exactly "
            f"{EXPECTED_SOURCE_ROWS} rows; found {len(rows)}."
        )

    if len(source_fields) != EXPECTED_SOURCE_FIELDS:
        raise RuntimeError(
            "Source must contain exactly "
            f"{EXPECTED_SOURCE_FIELDS} fields; "
            f"found {len(source_fields)}."
        )

    required_source_fields = {
        "secret_lair_id",
        "product_name",
        "automatic_purchase_execution",
        *AUTHORIZED_SOURCE_FIELDS,
    }

    missing = sorted(
        required_source_fields
        - set(source_fields)
    )

    if missing:
        raise RuntimeError(
            "Certified source is missing required fields: "
            + ", ".join(missing)
        )

    seen_ids: set[str] = set()
    seen_assets: set[str] = set()
    output_rows: list[dict[str, str]] = []

    source_path_text = (
        "docs/phase_8/secret_lair/"
        "secret_lair_v1_purchase_analysis.csv"
    )

    for row in rows:
        secret_lair_id = str(
            row.get("secret_lair_id", "")
        ).strip()

        if not secret_lair_id:
            raise RuntimeError(
                "Blank secret_lair_id is forbidden."
            )

        if secret_lair_id in seen_ids:
            raise RuntimeError(
                "Duplicate secret_lair_id: "
                f"{secret_lair_id}"
            )

        seen_ids.add(secret_lair_id)

        if strict_true(
            row.get("automatic_purchase_execution")
        ):
            raise RuntimeError(
                "Automatic purchase execution is forbidden: "
                f"{secret_lair_id}"
            )

        mtg_asset_id = (
            f"SECRET_LAIR_V1_1|{secret_lair_id}"
        )

        if mtg_asset_id in seen_assets:
            raise RuntimeError(
                "Duplicate mtg_asset_id: "
                f"{mtg_asset_id}"
            )

        seen_assets.add(mtg_asset_id)

        output: dict[str, str] = {
            "mtg_asset_id": mtg_asset_id,
            "secret_lair_id": secret_lair_id,
            "product_name": str(
                row.get("product_name", "")
            ),
        }

        for field in AUTHORIZED_SOURCE_FIELDS:
            output[field] = str(
                row.get(field, "")
            )

        output["source_authority_path"] = (
            source_path_text
        )

        output["source_authority_sha256"] = (
            source_sha
        )

        if set(output) != set(OUTPUT_FIELDS):
            raise RuntimeError(
                "Output field surface drift detected."
            )

        output_rows.append(output)

    if len(output_rows) != EXPECTED_SOURCE_ROWS:
        raise RuntimeError(
            "Premium sidecar output row count mismatch."
        )

    if len(seen_ids) != EXPECTED_SOURCE_ROWS:
        raise RuntimeError(
            "Premium sidecar source identity count mismatch."
        )

    if len(seen_assets) != EXPECTED_SOURCE_ROWS:
        raise RuntimeError(
            "Premium sidecar UIP identity count mismatch."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=OUTPUT_FIELDS,
            extrasaction="raise",
        )

        writer.writeheader()
        writer.writerows(output_rows)

    output_sha = sha256(OUTPUT)

    summary = {
        "contract_id":
            "MTG_SECRET_LAIR_PREMIUM_RESEARCH_SIDECAR_V1",
        "status":
            "CERTIFIED_SOURCE_SIDECAR_BUILT",
        "lane":
            "SECRET_LAIR_V1_1",
        "dataset_name":
            "mtg_secret_lair_premium_research",
        "filename":
            "mtg_secret_lair_premium_research.csv",
        "row_count":
            len(output_rows),
        "field_count":
            len(OUTPUT_FIELDS),
        "unique_secret_lair_id_count":
            len(seen_ids),
        "unique_mtg_asset_id_count":
            len(seen_assets),
        "source_authority_path":
            source_path_text,
        "source_authority_sha256":
            source_sha,
        "sidecar_sha256":
            output_sha,
        "one_year_semantic":
            "CERTIFIED_FORECAST_AND_EMPIRICAL_RISK",
        "three_year_semantic":
            "SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED",
        "five_year_semantic":
            "SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED",
        "q10_is_governed_purchase_entry_threshold":
            True,
        "automatic_purchase_execution_authorized":
            False,
        "source_values_recomputed":
            False,
        "source_values_synthesized":
            False,
        "existing_23_field_export_modified":
            False,
        "uip_ingestion_authorized":
            False,
        "database_write_authorized":
            False,
        "hosted_activation_authorized":
            False,
        "frontend_change_authorized":
            False,
    }

    SUMMARY.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return summary


def main() -> None:
    result = build()

    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
