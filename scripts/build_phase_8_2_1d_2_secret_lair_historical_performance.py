from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_HISTORY = (
    ROOT
    / "data"
    / "warehouse"
    / "current"
    / "secret_lair"
    / "master_secret_lair_price_history.csv"
)

DEFAULT_EVALUATION = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "ebay_matching"
    / "production_refresh"
    / "full_model_evaluation"
    / "secret_lair_full_model_evaluation.csv"
)

DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "validation"
    / "phase_8"
    / "secret_lair_historical_performance"
)

UNIVERSAL_LATEST = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "universal_export"
    / "latest"
)

UIP_LATEST = (
    ROOT
    / "data"
    / "operations"
    / "mtg_uip_delivery"
    / "latest"
)

MIN_DISTINCT_OBSERVATION_DATES = 2
MIN_ELAPSED_DAYS = 30

OUTPUT_FIELDS = [
    "investment_product_id",
    "universal_mtg_product_id",
    "canonical_product_name",
    "asset_class",
    "currency",
    "historical_performance_status",
    "historical_performance_eligible",
    "historical_start_date",
    "historical_end_date",
    "historical_start_value_usd",
    "historical_end_value_usd",
    "historical_elapsed_days",
    "historical_observation_count",
    "historical_distinct_dates",
    "historical_source_count",
    "historical_sources",
    "historical_total_return_pct",
    "historical_cagr_pct",
    "historical_annualized_return_pct",
    "historical_min_value_usd",
    "historical_max_value_usd",
    "historical_data_quality",
    "historical_suppression_reason",
    "forecast_eligible",
    "recommendation_eligible",
    "one_year_base_usd",
    "three_year_base_usd",
    "five_year_base_usd",
]


def clean(value: Any) -> str:
    # Preserve legitimate numeric zero values. Using ``value or ""`` turns
    # 0 and 0.0 into an empty string and incorrectly marks zero returns as
    # missing during in-memory certification.
    if value is None:
        return ""
    return str(value).strip()


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        value_float = float(text)
    except ValueError:
        return None
    if not math.isfinite(value_float):
        return None
    return value_float


def parse_date(value: Any) -> date | None:
    text = clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=OUTPUT_FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def canonical_daily_observations(
    history_rows: list[dict[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)

    for row in history_rows:
        product_id = clean(row.get("secret_lair_id"))
        observation_date = parse_date(row.get("observation_date"))
        market_price = number(row.get("market_price"))
        low_price = number(row.get("low_price"))

        selected_price = (
            market_price
            if market_price is not None and market_price > 0
            else low_price
        )

        if (
            not product_id
            or observation_date is None
            or selected_price is None
            or selected_price <= 0
        ):
            continue

        grouped[(product_id, observation_date)].append(
            {
                "value": float(selected_price),
                "source": clean(row.get("source_name")) or "UNKNOWN",
            }
        )

    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for (product_id, observation_date), records in grouped.items():
        values = [record["value"] for record in records]
        sources = sorted({record["source"] for record in records})
        by_product[product_id].append(
            {
                "date": observation_date,
                "value": round(float(median(values)), 2),
                "sources": sources,
                "raw_observations": len(records),
            }
        )

    for product_id in by_product:
        by_product[product_id].sort(key=lambda row: row["date"])

    return by_product


def historical_metrics(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    if not observations:
        return {
            "status": "NO_HISTORY",
            "eligible": "NO",
            "suppression_reason": "NO_VALID_DATED_PRICE_OBSERVATIONS",
            "quality": "NONE",
        }

    first = observations[0]
    last = observations[-1]
    elapsed_days = (last["date"] - first["date"]).days
    distinct_dates = len(observations)
    observation_count = sum(
        int(row["raw_observations"])
        for row in observations
    )
    sources = sorted(
        {
            source
            for row in observations
            for source in row["sources"]
        }
    )
    values = [float(row["value"]) for row in observations]

    base = {
        "start_date": first["date"].isoformat(),
        "end_date": last["date"].isoformat(),
        "start_value": round(float(first["value"]), 2),
        "end_value": round(float(last["value"]), 2),
        "elapsed_days": elapsed_days,
        "observation_count": observation_count,
        "distinct_dates": distinct_dates,
        "source_count": len(sources),
        "sources": "|".join(sources),
        "min_value": round(min(values), 2),
        "max_value": round(max(values), 2),
    }

    if distinct_dates < MIN_DISTINCT_OBSERVATION_DATES:
        return {
            **base,
            "status": "INSUFFICIENT_HISTORY",
            "eligible": "NO",
            "suppression_reason": "REQUIRES_AT_LEAST_TWO_DISTINCT_OBSERVATION_DATES",
            "quality": "SINGLE_SNAPSHOT",
        }

    if elapsed_days < MIN_ELAPSED_DAYS:
        return {
            **base,
            "status": "INSUFFICIENT_SPAN",
            "eligible": "NO",
            "suppression_reason": (
                f"REQUIRES_AT_LEAST_{MIN_ELAPSED_DAYS}_ELAPSED_DAYS"
            ),
            "quality": "SHORT_SPAN",
        }

    start_value = float(first["value"])
    end_value = float(last["value"])

    if start_value <= 0 or end_value <= 0:
        return {
            **base,
            "status": "INVALID_PRICE_SERIES",
            "eligible": "NO",
            "suppression_reason": "NONPOSITIVE_START_OR_END_VALUE",
            "quality": "INVALID",
        }

    total_return = end_value / start_value - 1.0
    elapsed_years = elapsed_days / 365.2425
    cagr = (
        (end_value / start_value) ** (1.0 / elapsed_years) - 1.0
        if elapsed_years > 0
        else None
    )

    if distinct_dates >= 12 and elapsed_days >= 365:
        quality = "STRONG"
    elif distinct_dates >= 6 and elapsed_days >= 180:
        quality = "MODERATE"
    else:
        quality = "LIMITED"

    return {
        **base,
        "status": "HISTORICAL_PERFORMANCE_READY",
        "eligible": "YES",
        "suppression_reason": "",
        "quality": quality,
        "total_return_pct": round(total_return * 100.0, 6),
        "cagr_pct": (
            round(float(cagr) * 100.0, 6)
            if cagr is not None and math.isfinite(cagr)
            else ""
        ),
        "annualized_return_pct": (
            round(float(cagr) * 100.0, 6)
            if cagr is not None and math.isfinite(cagr)
            else ""
        ),
    }


def build(
    history_path: Path,
    evaluation_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    if not history_path.is_file():
        raise FileNotFoundError(history_path)
    if not evaluation_path.is_file():
        raise FileNotFoundError(evaluation_path)

    history_rows = read_csv(history_path)
    evaluation_rows = read_csv(evaluation_path)

    if len(evaluation_rows) != 973:
        raise RuntimeError(
            "Secret Lair evaluation must contain 973 governed products; "
            f"found {len(evaluation_rows)}"
        )

    observations_by_product = canonical_daily_observations(history_rows)

    output_rows: list[dict[str, Any]] = []

    for product in evaluation_rows:
        product_id = clean(product.get("investment_product_id"))
        if not product_id:
            raise RuntimeError("Governed Secret Lair product is missing an ID.")

        metrics = historical_metrics(
            observations_by_product.get(product_id, [])
        )

        output_rows.append(
            {
                "investment_product_id": product_id,
                "universal_mtg_product_id": (
                    f"MTG:SECRET_LAIR:{product_id}"
                ),
                "canonical_product_name": clean(
                    product.get("canonical_product_name")
                ),
                "asset_class": "SECRET_LAIR",
                "currency": "USD",
                "historical_performance_status": metrics["status"],
                "historical_performance_eligible": metrics["eligible"],
                "historical_start_date": metrics.get("start_date", ""),
                "historical_end_date": metrics.get("end_date", ""),
                "historical_start_value_usd": metrics.get(
                    "start_value", ""
                ),
                "historical_end_value_usd": metrics.get(
                    "end_value", ""
                ),
                "historical_elapsed_days": metrics.get(
                    "elapsed_days", ""
                ),
                "historical_observation_count": metrics.get(
                    "observation_count", 0
                ),
                "historical_distinct_dates": metrics.get(
                    "distinct_dates", 0
                ),
                "historical_source_count": metrics.get(
                    "source_count", 0
                ),
                "historical_sources": metrics.get("sources", ""),
                "historical_total_return_pct": metrics.get(
                    "total_return_pct", ""
                ),
                "historical_cagr_pct": metrics.get("cagr_pct", ""),
                "historical_annualized_return_pct": metrics.get(
                    "annualized_return_pct", ""
                ),
                "historical_min_value_usd": metrics.get(
                    "min_value", ""
                ),
                "historical_max_value_usd": metrics.get(
                    "max_value", ""
                ),
                "historical_data_quality": metrics["quality"],
                "historical_suppression_reason": metrics[
                    "suppression_reason"
                ],
                # Historical analytics never changes forecast or
                # recommendation eligibility.
                "forecast_eligible": "NO",
                "recommendation_eligible": "NO",
                "one_year_base_usd": "",
                "three_year_base_usd": "",
                "five_year_base_usd": "",
            }
        )

    output_rows.sort(key=lambda row: row["investment_product_id"])

    output_path = output_root / "secret_lair_historical_performance.csv"
    write_csv(output_path, output_rows)

    universal_path = UNIVERSAL_LATEST / "historical_performance.csv"
    uip_path = UIP_LATEST / "historical_performance.csv"
    write_csv(universal_path, output_rows)
    write_csv(uip_path, output_rows)

    ready_rows = [
        row for row in output_rows
        if row["historical_performance_eligible"] == "YES"
    ]
    no_history_rows = [
        row for row in output_rows
        if row["historical_performance_status"] == "NO_HISTORY"
    ]
    insufficient_rows = [
        row for row in output_rows
        if row["historical_performance_status"] in {
            "INSUFFICIENT_HISTORY",
            "INSUFFICIENT_SPAN",
        }
    ]

    checks = {
        "rows_equal_973": len(output_rows) == 973,
        "ids_unique": len(
            {row["investment_product_id"] for row in output_rows}
        ) == 973,
        "historical_and_forecast_semantics_separated": all(
            row["forecast_eligible"] == "NO"
            and row["recommendation_eligible"] == "NO"
            and not clean(row["one_year_base_usd"])
            and not clean(row["three_year_base_usd"])
            and not clean(row["five_year_base_usd"])
            for row in output_rows
        ),
        "returns_only_when_history_eligible": all(
            (
                clean(row["historical_total_return_pct"])
                and clean(row["historical_cagr_pct"])
            )
            if row["historical_performance_eligible"] == "YES"
            else (
                not clean(row["historical_total_return_pct"])
                and not clean(row["historical_cagr_pct"])
            )
            for row in output_rows
        ),
        "ready_rows_have_two_dates_and_minimum_span": all(
            int(row["historical_distinct_dates"])
            >= MIN_DISTINCT_OBSERVATION_DATES
            and int(row["historical_elapsed_days"])
            >= MIN_ELAPSED_DAYS
            for row in ready_rows
        ),
        "universal_export_written": universal_path.is_file(),
        "uip_delivery_written": uip_path.is_file(),
    }

    status = "CERTIFIED" if all(checks.values()) else "FAILED"

    manifest = {
        "status": status,
        "phase": "8.2.1D.2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_history": str(history_path),
        "source_evaluation": str(evaluation_path),
        "governed_products": len(output_rows),
        "history_source_rows": len(history_rows),
        "history_ready_products": len(ready_rows),
        "insufficient_history_products": len(insufficient_rows),
        "no_history_products": len(no_history_rows),
        "minimum_distinct_dates": MIN_DISTINCT_OBSERVATION_DATES,
        "minimum_elapsed_days": MIN_ELAPSED_DAYS,
        "checks": checks,
        "outputs": {
            "historical_performance": str(output_path),
            "universal_export": str(universal_path),
            "uip_delivery": str(uip_path),
        },
    }

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        output_root
        / "PHASE_8_2_1D_2_HISTORICAL_PERFORMANCE_MANIFEST.json"
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    certification_path = (
        output_root
        / "PHASE_8_2_1D_2_HISTORICAL_PERFORMANCE_CERTIFICATION.md"
    )
    lines = [
        "# Phase 8.2.1D.2 — Secret Lair Historical Performance",
        "",
        f"**Status:** {status}",
        "",
        "## Counts",
        "",
        f"- Governed products: {len(output_rows)}",
        f"- History source rows: {len(history_rows)}",
        f"- Historical-performance ready: {len(ready_rows)}",
        f"- Insufficient history: {len(insufficient_rows)}",
        f"- No valid history: {len(no_history_rows)}",
        "",
        "## Governance",
        "",
        "- Historical returns are calculated only from dated observed values.",
        "- At least two distinct dates and 30 elapsed days are required.",
        "- Historical CAGR never populates forward forecast horizons.",
        "- Historical analytics never enables recommendations.",
        "",
        "## Checks",
        "",
    ]
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )
    certification_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("=" * 78)
    print("PHASE 8.2.1D.2 — SECRET LAIR HISTORICAL PERFORMANCE")
    print("=" * 78)
    print(f"Governed products: {len(output_rows)}")
    print(f"History source rows: {len(history_rows)}")
    print(f"Historical-performance ready: {len(ready_rows)}")
    print(f"Insufficient history: {len(insufficient_rows)}")
    print(f"No valid history: {len(no_history_rows)}")
    print(f"Status: {status}")
    print(f"Output: {output_path}")
    print(f"Universal delivery: {universal_path}")
    print(f"UIP delivery: {uip_path}")
    print(
        "PHASE 8.2.1D.2 HISTORICAL PERFORMANCE: "
        f"{status}"
    )

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY,
    )
    parser.add_argument(
        "--evaluation",
        type=Path,
        default=DEFAULT_EVALUATION,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()

    result = build(
        args.history,
        args.evaluation,
        args.output_root,
    )
    return 0 if result["status"] == "CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
