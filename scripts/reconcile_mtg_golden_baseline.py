from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ROOT = (
    ROOT
    / "docs"
    / "phase_8"
    / "mtg_intelligence_recovery"
    / "golden_baseline"
)

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

BASELINE_PRODUCTS_CSV = OUTPUT_ROOT / "golden_baseline_products.csv"
CURRENT_SOURCE_INVENTORY_CSV = OUTPUT_ROOT / "current_source_inventory.csv"
MATCHES_CSV = OUTPUT_ROOT / "golden_to_current_matches.csv"
FIELD_RECONCILIATION_CSV = OUTPUT_ROOT / "golden_field_reconciliation.csv"
PRODUCT_SUMMARY_CSV = OUTPUT_ROOT / "golden_product_summary.csv"
UNMATCHED_BASELINE_CSV = OUTPUT_ROOT / "unmatched_golden_products.csv"
DUPLICATE_IDENTITY_CSV = OUTPUT_ROOT / "duplicate_current_identities.csv"
SEMANTIC_ALERTS_CSV = OUTPUT_ROOT / "forecast_semantic_alerts.csv"
SUMMARY_JSON = OUTPUT_ROOT / "golden_baseline_reconciliation.json"
REPORT_MD = OUTPUT_ROOT / "PHASE_8_2_1B_GOLDEN_BASELINE_RECONCILIATION.md"

SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

SKIP_PATH_TERMS = {
    "/archive/",
    "/archives/",
    "/backup/",
    "/backups/",
    "/promotion_backups/",
    "/validation/",
    "/staging/",
    "/raw/",
    "/cache/",
}

PREFERRED_PATH_TERMS = (
    "latest",
    "current",
    "production",
    "dashboard",
    "delivery",
    "handoff",
    "governed",
    "universal",
    "forecast",
    "intelligence",
    "asset_master",
    "recommendation",
    "risk",
)

ID_ALIASES = {
    "id",
    "product_id",
    "tcgplayer_product_id",
    "tcgcsv_product_id",
    "source_product_id",
    "asset_id",
    "canonical_asset_id",
    "canonical_product_id",
    "universal_asset_id",
    "mtg_asset_id",
}

NAME_ALIASES = {
    "name",
    "product",
    "product_name",
    "asset_name",
    "canonical_name",
    "display_name",
    "drop_name",
    "title",
}

CLASS_ALIASES = {
    "class",
    "asset_class",
    "asset_subclass",
    "product_type",
    "category",
    "universe",
    "sealed_type",
}

FIELD_ALIASES = {
    "reference_price": {
        "reference_price",
        "current_price",
        "market_price",
        "latest_price",
        "observed_price",
        "price",
        "price_usd",
    },
    "price_as_of": {
        "price_as_of",
        "as_of_date",
        "observation_date",
        "data_as_of_date",
        "snapshot_date",
        "latest_price_date",
    },
    "forecast_horizon_months": {
        "forecast_horizon_months",
        "horizon_months",
        "forecast_months",
        "projection_horizon_months",
    },
    "point_forecast": {
        "point_forecast",
        "projected_price",
        "forecast_price",
        "forecast_value",
        "projected_value",
        "median_forecast",
    },
    "lower_bound": {
        "lower_bound",
        "forecast_low",
        "projected_low",
        "low_estimate",
        "p05",
        "p10",
    },
    "upper_bound": {
        "upper_bound",
        "forecast_high",
        "projected_high",
        "high_estimate",
        "p90",
        "p95",
    },
    "expected_return": {
        "expected_return",
        "projected_return",
        "forecast_return",
        "expected_return_pct",
        "projected_return_pct",
    },
    "forecast_cagr": {
        "forecast_cagr",
        "projected_cagr",
        "expected_cagr",
        "modeled_cagr",
    },
    "realized_annualized_return": {
        "realized_annualized_return",
        "annualized_return",
        "annualized_return_pct",
        "historical_cagr",
        "realized_cagr",
        "ann_return",
        "annret",
    },
    "return_1y": {
        "return_1y",
        "one_year_return",
        "return_365d",
        "trailing_1y_return",
        "r365",
    },
    "confidence_score": {
        "confidence_score",
        "forecast_confidence",
        "confidence",
        "conf",
    },
    "recommendation": {
        "recommendation",
        "rating",
        "signal",
        "conviction_tier",
        "conv_tier",
    },
    "investment_score": {
        "investment_score",
        "model_score",
        "score",
    },
    "risk_score": {
        "risk_score",
        "risk",
    },
    "maximum_drawdown": {
        "maximum_drawdown",
        "max_drawdown",
        "drawdown",
        "peak_drawdown",
        "dd",
    },
}

NUMERIC_FIELDS = {
    "reference_price",
    "forecast_horizon_months",
    "point_forecast",
    "lower_bound",
    "upper_bound",
    "expected_return",
    "forecast_cagr",
    "realized_annualized_return",
    "return_1y",
    "confidence_score",
    "investment_score",
    "risk_score",
    "maximum_drawdown",
}

PRICE_FIELDS = {
    "reference_price",
    "point_forecast",
    "lower_bound",
    "upper_bound",
}

PERCENT_FIELDS = {
    "expected_return",
    "forecast_cagr",
    "realized_annualized_return",
    "return_1y",
    "confidence_score",
    "maximum_drawdown",
}


def norm(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value or "").strip().lower(),
    ).strip("_")


def norm_name(value: Any) -> str:
    text = str(value or "").lower()

    replacements = {
        "&": " and ",
        "collector booster box": "collector booster display",
        "booster box": "booster display",
        "secret lair drop series": "secret lair",
        "non foil": "nonfoil",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def product_number(value: Any) -> str:
    text = str(value or "").strip()

    match = re.search(r"(\d{4,})$", text)

    return match.group(1) if match else ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def parse_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return float(value)

    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None

        return float(value)

    text = str(value).strip()

    if not text:
        return None

    text = text.replace("$", "").replace(",", "").replace("%", "")

    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]

    try:
        return float(text)
    except ValueError:
        return None


def normalize_fraction(
    value: float | None,
    field: str,
) -> float | None:
    if value is None:
        return None

    if field in PERCENT_FIELDS and abs(value) > 2:
        return value / 100.0

    return value


def first_present(
    record: dict[str, Any],
    aliases: Iterable[str],
) -> Any:
    normalized_record = {
        norm(key): value
        for key, value in record.items()
    }

    for alias in aliases:
        candidate = normalized_record.get(norm(alias))

        if candidate not in (None, ""):
            return candidate

    return None


def extract_data_object(html: str) -> dict[str, Any]:
    match = re.search(r"\bconst\s+DATA\s*=\s*", html)

    if not match:
        raise RuntimeError(
            "Could not locate embedded `const DATA =` object "
            "in the golden terminal."
        )

    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(html[match.end():])

    if not isinstance(data, dict):
        raise RuntimeError("Embedded DATA object is not a JSON object.")

    return data


def baseline_row(
    raw: dict[str, Any],
    universe: str,
) -> dict[str, Any]:
    raw_id = (
        raw.get("id")
        or raw.get("product_id")
        or raw.get("asset_id")
        or ""
    )

    name = (
        raw.get("name")
        or raw.get("product_name")
        or raw.get("drop_name")
        or ""
    )

    row = {
        "baseline_universe": universe,
        "baseline_id": str(raw_id),
        "baseline_product_number": product_number(raw_id),
        "baseline_name": str(name),
        "baseline_name_normalized": norm_name(name),
        "baseline_class": (
            raw.get("type")
            or raw.get("cls")
            or raw.get("class")
            or universe
        ),
        "baseline_reference_price": parse_float(raw.get("price")),
        "baseline_price_as_of": "",
        "baseline_forecast_cagr": None,
        "baseline_realized_annualized_return": None,
        "baseline_return_1y": parse_float(
            raw.get("r365")
            if raw.get("r365") is not None
            else raw.get("return_1y")
        ),
        "baseline_forecast_1y_point": None,
        "baseline_forecast_1y_low": None,
        "baseline_forecast_1y_high": None,
        "baseline_forecast_3y_point": None,
        "baseline_forecast_3y_low": None,
        "baseline_forecast_3y_high": None,
        "baseline_forecast_5y_point": None,
        "baseline_forecast_5y_low": None,
        "baseline_forecast_5y_high": None,
        "baseline_confidence": parse_float(raw.get("conf")),
        "baseline_recommendation": (
            raw.get("convTier")
            or raw.get("rating")
            or raw.get("signal")
            or ""
        ),
        "baseline_investment_score": parse_float(raw.get("score")),
        "baseline_risk_score": parse_float(raw.get("riskScore")),
        "baseline_maximum_drawdown": parse_float(raw.get("dd")),
        "baseline_source_fields_json": json.dumps(
            sorted(raw.keys())
        ),
    }

    if universe == "booster":
        cagr = parse_float(raw.get("cagr"))
        row["baseline_forecast_cagr"] = cagr

        current = row["baseline_reference_price"]

        if current is not None and cagr is not None:
            for years in (1, 3):
                point = current * ((1.0 + cagr) ** years)
                row[f"baseline_forecast_{years}y_point"] = point

        row["baseline_forecast_5y_point"] = parse_float(
            raw.get("med5")
        )
        row["baseline_forecast_5y_low"] = parse_float(
            raw.get("p05")
        )
        row["baseline_forecast_5y_high"] = parse_float(
            raw.get("p95")
        )

    else:
        row["baseline_realized_annualized_return"] = parse_float(
            raw.get("annRet")
            if raw.get("annRet") is not None
            else raw.get("annualized_return")
        )

    return row


def should_scan(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False

    if any(part in SKIP_PARTS for part in path.parts):
        return False

    relative = "/" + path.relative_to(ROOT).as_posix().lower() + "/"

    if any(term in relative for term in SKIP_PATH_TERMS):
        return False

    if path.stat().st_size == 0:
        return False

    return True


def source_priority(path: Path) -> int:
    relative = path.relative_to(ROOT).as_posix().lower()

    score = 0

    for index, term in enumerate(PREFERRED_PATH_TERMS):
        if term in relative:
            score += len(PREFERRED_PATH_TERMS) - index

    if "latest" in relative:
        score += 20

    if "phase_11e" in relative:
        score += 15

    return score


def identify_columns(
    columns: list[str],
) -> dict[str, str]:
    normalized = {norm(column): column for column in columns}

    result: dict[str, str] = {}

    for alias in ID_ALIASES:
        if norm(alias) in normalized:
            result["identity_id"] = normalized[norm(alias)]
            break

    for alias in NAME_ALIASES:
        if norm(alias) in normalized:
            result["identity_name"] = normalized[norm(alias)]
            break

    for alias in CLASS_ALIASES:
        if norm(alias) in normalized:
            result["identity_class"] = normalized[norm(alias)]
            break

    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if norm(alias) in normalized:
                result[canonical] = normalized[norm(alias)]
                break

    return result


def is_candidate_schema(mapping: dict[str, str]) -> bool:
    identity_present = (
        "identity_id" in mapping
        or "identity_name" in mapping
    )

    metric_count = sum(
        field in mapping
        for field in FIELD_ALIASES
    )

    return identity_present and metric_count > 0


def parse_current_record(
    row: dict[str, Any],
    mapping: dict[str, str],
    source_path: Path,
    row_number: int,
) -> dict[str, Any]:
    raw_id = row.get(mapping.get("identity_id", ""), "")
    raw_name = row.get(mapping.get("identity_name", ""), "")
    raw_class = row.get(mapping.get("identity_class", ""), "")

    result: dict[str, Any] = {
        "current_source_path": source_path.relative_to(ROOT).as_posix(),
        "current_source_priority": source_priority(source_path),
        "current_row_number": row_number,
        "current_id": str(raw_id or ""),
        "current_product_number": product_number(raw_id),
        "current_name": str(raw_name or ""),
        "current_name_normalized": norm_name(raw_name),
        "current_class": str(raw_class or ""),
    }

    for canonical, source_column in mapping.items():
        if canonical.startswith("identity_"):
            continue

        value = row.get(source_column)

        if canonical in NUMERIC_FIELDS:
            numeric = normalize_fraction(
                parse_float(value),
                canonical,
            )
            result[f"current_{canonical}"] = numeric

        else:
            result[f"current_{canonical}"] = str(value or "")

    result["current_columns_json"] = json.dumps(mapping)
    return result


def identity_key(record: dict[str, Any]) -> tuple[str, str]:
    number = str(
        record.get("current_product_number")
        or record.get("baseline_product_number")
        or ""
    )

    name = str(
        record.get("current_name_normalized")
        or record.get("baseline_name_normalized")
        or ""
    )

    return number, name


def match_type(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> str | None:
    baseline_number = baseline["baseline_product_number"]
    current_number = current["current_product_number"]

    if (
        baseline_number
        and current_number
        and baseline_number == current_number
    ):
        return "EXACT_PRODUCT_NUMBER"

    if (
        baseline["baseline_id"]
        and current["current_id"]
        and norm(baseline["baseline_id"]) == norm(current["current_id"])
    ):
        return "EXACT_ID"

    if (
        baseline["baseline_name_normalized"]
        and baseline["baseline_name_normalized"]
        == current["current_name_normalized"]
    ):
        return "EXACT_NORMALIZED_NAME"

    return None


def relative_difference(
    baseline: float | None,
    current: float | None,
) -> float | None:
    if baseline is None or current is None:
        return None

    if baseline == 0:
        return None

    return (current - baseline) / abs(baseline)


def absolute_difference(
    baseline: float | None,
    current: float | None,
) -> float | None:
    if baseline is None or current is None:
        return None

    return current - baseline


def field_status(
    field: str,
    baseline: float | str | None,
    current: float | str | None,
) -> tuple[str, str]:
    if baseline in (None, "") and current in (None, ""):
        return "NOT_APPLICABLE", ""

    if baseline not in (None, "") and current in (None, ""):
        return "MISSING_CURRENT", "Golden value is not present in current output."

    if baseline in (None, "") and current not in (None, ""):
        return "CURRENT_ONLY", "No equivalent golden value exists."

    if field in NUMERIC_FIELDS:
        b = parse_float(baseline)
        c = parse_float(current)

        if b is None or c is None:
            return "TYPE_MISMATCH", "Numeric comparison could not be computed."

        rel = relative_difference(b, c)
        abs_diff = abs(c - b)

        if field in PRICE_FIELDS:
            tolerance = max(2.0, abs(b) * 0.08)

            if abs_diff <= tolerance:
                return "PASS", "Within $2 or 8% price tolerance."

            if abs_diff <= max(10.0, abs(b) * 0.20):
                return "REVIEW", "Outside normal tolerance but within 20%."

            return "FAIL", "Price differs by more than 20%."

        if field == "forecast_horizon_months":
            if abs_diff < 0.001:
                return "PASS", "Forecast horizon matches exactly."

            return "FAIL", "Forecast horizon differs."

        if field in PERCENT_FIELDS:
            tolerance = 0.03

            if abs_diff <= tolerance:
                return "PASS", "Within 3 percentage points."

            if abs_diff <= 0.10:
                return "REVIEW", "Differs by 3–10 percentage points."

            return "FAIL", "Differs by more than 10 percentage points."

        if rel is not None and abs(rel) <= 0.10:
            return "PASS", "Within 10%."

        if rel is not None and abs(rel) <= 0.25:
            return "REVIEW", "Differs by 10–25%."

        return "FAIL", "Differs by more than 25%."

    if norm(baseline) == norm(current):
        return "PASS", "Text values match after normalization."

    return "REVIEW", "Text values differ."


def best_current_rows(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            item["current_source_priority"],
            bool(item.get("current_reference_price") is not None),
            bool(item.get("current_point_forecast") is not None),
            bool(item.get("current_expected_return") is not None),
        ),
        reverse=True,
    )


parser = argparse.ArgumentParser()
parser.add_argument(
    "--baseline-html",
    required=True,
    type=Path,
)
args = parser.parse_args()

baseline_html = args.baseline_html.resolve()

if not baseline_html.is_file():
    raise FileNotFoundError(
        f"Golden terminal not found: {baseline_html}"
    )

html_text = baseline_html.read_text(
    encoding="utf-8",
    errors="replace",
)

data = extract_data_object(html_text)

boosters = [
    item
    for item in data.get("boosters", [])
    if isinstance(item, dict)
]

secret_lairs = []

for key in ("sl", "secret_lairs", "secretLairs"):
    values = data.get(key)

    if isinstance(values, list):
        secret_lairs.extend(
            item for item in values if isinstance(item, dict)
        )

baseline = [
    baseline_row(item, "booster")
    for item in boosters
]

baseline.extend(
    baseline_row(item, "secret_lair")
    for item in secret_lairs
)

baseline_fields = list(baseline[0].keys()) if baseline else []

with BASELINE_PRODUCTS_CSV.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=baseline_fields,
    )
    writer.writeheader()
    writer.writerows(baseline)

source_inventory: list[dict[str, Any]] = []
current_records: list[dict[str, Any]] = []

csv_paths = sorted(
    (
        path
        for path in ROOT.rglob("*.csv")
        if should_scan(path)
    ),
    key=source_priority,
    reverse=True,
)

for path in csv_paths:
    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            mapping = identify_columns(columns)

            if not is_candidate_schema(mapping):
                continue

            source_count = 0

            for row_number, row in enumerate(reader, start=2):
                parsed = parse_current_record(
                    row,
                    mapping,
                    path,
                    row_number,
                )

                if (
                    not parsed["current_id"]
                    and not parsed["current_name"]
                ):
                    continue

                current_records.append(parsed)
                source_count += 1

            source_inventory.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "priority": source_priority(path),
                    "file_size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                    "row_count_read": source_count,
                    "columns": json.dumps(columns),
                    "mapped_columns": json.dumps(mapping),
                }
            )

    except Exception as exc:
        source_inventory.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "priority": source_priority(path),
                "file_size_bytes": path.stat().st_size,
                "sha256": "",
                "row_count_read": 0,
                "columns": "",
                "mapped_columns": "",
                "error": str(exc),
            }
        )

inventory_fields = sorted(
    {
        key
        for item in source_inventory
        for key in item.keys()
    }
)

with CURRENT_SOURCE_INVENTORY_CSV.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=inventory_fields,
    )
    writer.writeheader()
    writer.writerows(source_inventory)

by_number: dict[str, list[dict[str, Any]]] = defaultdict(list)
by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)

for record in current_records:
    if record["current_product_number"]:
        by_number[record["current_product_number"]].append(record)

    if record["current_name_normalized"]:
        by_name[record["current_name_normalized"]].append(record)

match_rows: list[dict[str, Any]] = []
field_rows: list[dict[str, Any]] = []
product_rows: list[dict[str, Any]] = []
unmatched_rows: list[dict[str, Any]] = []
semantic_alerts: list[dict[str, Any]] = []

comparison_map = {
    "reference_price": "baseline_reference_price",
    "forecast_cagr": "baseline_forecast_cagr",
    "realized_annualized_return": (
        "baseline_realized_annualized_return"
    ),
    "return_1y": "baseline_return_1y",
    "confidence_score": "baseline_confidence",
    "recommendation": "baseline_recommendation",
    "investment_score": "baseline_investment_score",
    "risk_score": "baseline_risk_score",
    "maximum_drawdown": "baseline_maximum_drawdown",
}

for item in baseline:
    candidates: list[dict[str, Any]] = []

    if item["baseline_product_number"]:
        candidates.extend(
            by_number.get(
                item["baseline_product_number"],
                [],
            )
        )

    if item["baseline_name_normalized"]:
        candidates.extend(
            by_name.get(
                item["baseline_name_normalized"],
                [],
            )
        )

    deduped: dict[tuple[str, int], dict[str, Any]] = {}

    for candidate in candidates:
        key = (
            candidate["current_source_path"],
            candidate["current_row_number"],
        )
        deduped[key] = candidate

    candidates = best_current_rows(list(deduped.values()))

    if not candidates:
        unmatched_rows.append(item)
        product_rows.append(
            {
                "baseline_id": item["baseline_id"],
                "baseline_name": item["baseline_name"],
                "baseline_universe": item["baseline_universe"],
                "matched_source_count": 0,
                "field_pass_count": 0,
                "field_review_count": 0,
                "field_fail_count": 1,
                "overall_status": "FAIL",
                "primary_issue": "No current product match found.",
            }
        )
        continue

    pass_count = 0
    review_count = 0
    fail_count = 0

    for candidate_rank, candidate in enumerate(
        candidates,
        start=1,
    ):
        kind = match_type(item, candidate)

        if not kind:
            continue

        match_rows.append(
            {
                "baseline_id": item["baseline_id"],
                "baseline_product_number": (
                    item["baseline_product_number"]
                ),
                "baseline_name": item["baseline_name"],
                "baseline_universe": item["baseline_universe"],
                "current_source_path": (
                    candidate["current_source_path"]
                ),
                "current_row_number": (
                    candidate["current_row_number"]
                ),
                "current_id": candidate["current_id"],
                "current_product_number": (
                    candidate["current_product_number"]
                ),
                "current_name": candidate["current_name"],
                "match_type": kind,
                "candidate_rank": candidate_rank,
                "source_priority": (
                    candidate["current_source_priority"]
                ),
            }
        )

        for field, baseline_key in comparison_map.items():
            current_key = f"current_{field}"

            if current_key not in candidate:
                continue

            baseline_value = item.get(baseline_key)
            current_value = candidate.get(current_key)

            status, note = field_status(
                field,
                baseline_value,
                current_value,
            )

            if status == "PASS":
                pass_count += 1
            elif status == "REVIEW":
                review_count += 1
            elif status in {
                "FAIL",
                "MISSING_CURRENT",
                "TYPE_MISMATCH",
            }:
                fail_count += 1

            field_rows.append(
                {
                    "baseline_id": item["baseline_id"],
                    "baseline_name": item["baseline_name"],
                    "baseline_universe": (
                        item["baseline_universe"]
                    ),
                    "current_source_path": (
                        candidate["current_source_path"]
                    ),
                    "current_row_number": (
                        candidate["current_row_number"]
                    ),
                    "match_type": kind,
                    "candidate_rank": candidate_rank,
                    "field": field,
                    "baseline_value": baseline_value,
                    "current_value": current_value,
                    "absolute_difference": absolute_difference(
                        parse_float(baseline_value),
                        parse_float(current_value),
                    ),
                    "relative_difference": relative_difference(
                        parse_float(baseline_value),
                        parse_float(current_value),
                    ),
                    "status": status,
                    "note": note,
                }
            )

        horizon = candidate.get(
            "current_forecast_horizon_months"
        )
        expected_return = candidate.get(
            "current_expected_return"
        )
        point_forecast = candidate.get(
            "current_point_forecast"
        )
        reference_price = candidate.get(
            "current_reference_price"
        )
        lower = candidate.get("current_lower_bound")
        upper = candidate.get("current_upper_bound")
        cagr = candidate.get("current_forecast_cagr")
        realized = candidate.get(
            "current_realized_annualized_return"
        )

        if (
            horizon is not None
            and reference_price not in (None, 0)
            and point_forecast is not None
        ):
            implied_return = (
                point_forecast / reference_price
            ) - 1.0

            if (
                expected_return is not None
                and abs(implied_return - expected_return) > 0.05
            ):
                semantic_alerts.append(
                    {
                        "severity": "FAIL",
                        "alert_type": (
                            "EXPECTED_RETURN_POINT_FORECAST_MISMATCH"
                        ),
                        "baseline_id": item["baseline_id"],
                        "baseline_name": item["baseline_name"],
                        "current_source_path": (
                            candidate["current_source_path"]
                        ),
                        "current_row_number": (
                            candidate["current_row_number"]
                        ),
                        "horizon_months": horizon,
                        "reference_price": reference_price,
                        "point_forecast": point_forecast,
                        "expected_return": expected_return,
                        "implied_return": implied_return,
                        "details": (
                            "Expected return differs from the return "
                            "implied by point forecast and reference price."
                        ),
                    }
                )

        if (
            lower is not None
            and upper is not None
            and lower > upper
        ):
            semantic_alerts.append(
                {
                    "severity": "FAIL",
                    "alert_type": "REVERSED_FORECAST_INTERVAL",
                    "baseline_id": item["baseline_id"],
                    "baseline_name": item["baseline_name"],
                    "current_source_path": (
                        candidate["current_source_path"]
                    ),
                    "current_row_number": (
                        candidate["current_row_number"]
                    ),
                    "horizon_months": horizon,
                    "reference_price": reference_price,
                    "point_forecast": point_forecast,
                    "expected_return": expected_return,
                    "implied_return": "",
                    "details": "Lower bound exceeds upper bound.",
                }
            )

        if (
            point_forecast is not None
            and lower is not None
            and upper is not None
            and not (lower <= point_forecast <= upper)
        ):
            semantic_alerts.append(
                {
                    "severity": "REVIEW",
                    "alert_type": "POINT_OUTSIDE_INTERVAL",
                    "baseline_id": item["baseline_id"],
                    "baseline_name": item["baseline_name"],
                    "current_source_path": (
                        candidate["current_source_path"]
                    ),
                    "current_row_number": (
                        candidate["current_row_number"]
                    ),
                    "horizon_months": horizon,
                    "reference_price": reference_price,
                    "point_forecast": point_forecast,
                    "expected_return": expected_return,
                    "implied_return": "",
                    "details": (
                        "Point forecast is outside its stated interval."
                    ),
                }
            )

        if (
            horizon == 12
            and expected_return is not None
            and abs(expected_return) >= 1.5
        ):
            semantic_alerts.append(
                {
                    "severity": "REVIEW",
                    "alert_type": "EXTREME_ONE_YEAR_RETURN",
                    "baseline_id": item["baseline_id"],
                    "baseline_name": item["baseline_name"],
                    "current_source_path": (
                        candidate["current_source_path"]
                    ),
                    "current_row_number": (
                        candidate["current_row_number"]
                    ),
                    "horizon_months": horizon,
                    "reference_price": reference_price,
                    "point_forecast": point_forecast,
                    "expected_return": expected_return,
                    "implied_return": "",
                    "details": (
                        "Absolute one-year expected return is at least 150%."
                    ),
                }
            )

        if (
            cagr is not None
            and realized is not None
            and abs(cagr - realized) < 1e-12
            and item["baseline_universe"] == "secret_lair"
        ):
            semantic_alerts.append(
                {
                    "severity": "REVIEW",
                    "alert_type": "REALIZED_RETURN_EQUALS_FORECAST_CAGR",
                    "baseline_id": item["baseline_id"],
                    "baseline_name": item["baseline_name"],
                    "current_source_path": (
                        candidate["current_source_path"]
                    ),
                    "current_row_number": (
                        candidate["current_row_number"]
                    ),
                    "horizon_months": horizon,
                    "reference_price": reference_price,
                    "point_forecast": point_forecast,
                    "expected_return": expected_return,
                    "implied_return": "",
                    "details": (
                        "Secret Lair realized annualized return appears "
                        "identical to forward forecast CAGR."
                    ),
                }
            )

    if fail_count:
        overall = "FAIL"
    elif review_count:
        overall = "REVIEW"
    else:
        overall = "PASS"

    product_rows.append(
        {
            "baseline_id": item["baseline_id"],
            "baseline_name": item["baseline_name"],
            "baseline_universe": item["baseline_universe"],
            "matched_source_count": len(candidates),
            "field_pass_count": pass_count,
            "field_review_count": review_count,
            "field_fail_count": fail_count,
            "overall_status": overall,
            "primary_issue": (
                "One or more fields failed parity."
                if fail_count
                else (
                    "One or more fields require review."
                    if review_count
                    else ""
                )
            ),
        }
    )

duplicate_counter = Counter(
    (
        record["current_product_number"],
        record["current_name_normalized"],
        record["current_source_path"],
    )
    for record in current_records
)

duplicate_rows = [
    {
        "current_product_number": key[0],
        "current_name_normalized": key[1],
        "current_source_path": key[2],
        "duplicate_row_count": count,
    }
    for key, count in duplicate_counter.items()
    if count > 1
]

def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fields = sorted(
        {
            key
            for row in rows
            for key in row.keys()
        }
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


write_csv(MATCHES_CSV, match_rows)
write_csv(FIELD_RECONCILIATION_CSV, field_rows)
write_csv(PRODUCT_SUMMARY_CSV, product_rows)
write_csv(UNMATCHED_BASELINE_CSV, unmatched_rows)
write_csv(DUPLICATE_IDENTITY_CSV, duplicate_rows)
write_csv(SEMANTIC_ALERTS_CSV, semantic_alerts)

status_counts = Counter(
    row["overall_status"]
    for row in product_rows
)

alert_counts = Counter(
    row["alert_type"]
    for row in semantic_alerts
)

aftermath = [
    row
    for row in product_rows
    if "aftermath collector booster" in row["baseline_name"].lower()
]

summary = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "repository_root": str(ROOT),
    "baseline_html": str(baseline_html),
    "baseline_html_sha256": sha256(baseline_html),
    "baseline_booster_count": len(boosters),
    "baseline_secret_lair_count": len(secret_lairs),
    "baseline_total_count": len(baseline),
    "candidate_csv_source_count": len(source_inventory),
    "current_candidate_row_count": len(current_records),
    "matched_row_count": len(match_rows),
    "unmatched_baseline_count": len(unmatched_rows),
    "product_status_counts": dict(status_counts),
    "semantic_alert_count": len(semantic_alerts),
    "semantic_alert_counts": dict(alert_counts),
    "duplicate_identity_count": len(duplicate_rows),
    "aftermath_product_summary": aftermath,
    "outputs": {
        "baseline_products": str(BASELINE_PRODUCTS_CSV),
        "source_inventory": str(CURRENT_SOURCE_INVENTORY_CSV),
        "matches": str(MATCHES_CSV),
        "field_reconciliation": str(FIELD_RECONCILIATION_CSV),
        "product_summary": str(PRODUCT_SUMMARY_CSV),
        "unmatched_baseline": str(UNMATCHED_BASELINE_CSV),
        "duplicate_identities": str(DUPLICATE_IDENTITY_CSV),
        "semantic_alerts": str(SEMANTIC_ALERTS_CSV),
        "report": str(REPORT_MD),
    },
}

SUMMARY_JSON.write_text(
    json.dumps(summary, indent=2, default=str) + "\n",
    encoding="utf-8",
)

report = f"""# Phase 8.2.1B — Golden Baseline Reconciliation

## Status

Reconciliation completed in read-only mode.

## Golden baseline

- Booster products: **{len(boosters)}**
- Secret Lair products: **{len(secret_lairs)}**
- Total products: **{len(baseline)}**
- Baseline SHA-256: `{summary['baseline_html_sha256']}`

## Current-state scan

- Candidate current CSV sources: **{len(source_inventory)}**
- Candidate current rows: **{len(current_records)}**
- Matched baseline/current rows: **{len(match_rows)}**
- Unmatched golden products: **{len(unmatched_rows)}**
- Duplicate current identities: **{len(duplicate_rows)}**

## Product parity results

- PASS: **{status_counts.get('PASS', 0)}**
- REVIEW: **{status_counts.get('REVIEW', 0)}**
- FAIL: **{status_counts.get('FAIL', 0)}**

## Forecast-semantic alerts

- Total alerts: **{len(semantic_alerts)}**

{json.dumps(dict(alert_counts), indent=2)}

## Certification interpretation

This audit does not certify current MTG forecasts as correct.

A current output is considered unsafe when any of the following occurs:

1. Product identity does not match the golden product.
2. Reference price differs materially without a newer valid source date.
3. Forecast horizon is missing or inconsistent.
4. Expected return does not reconcile to reference price and point forecast.
5. A one-year field appears to contain a multi-year valuation.
6. Realized Secret Lair returns are mapped into forward CAGR fields.
7. Current outputs omit golden intelligence without an explicit suppression reason.

## Evidence

- `golden_baseline_products.csv`
- `current_source_inventory.csv`
- `golden_to_current_matches.csv`
- `golden_field_reconciliation.csv`
- `golden_product_summary.csv`
- `unmatched_golden_products.csv`
- `duplicate_current_identities.csv`
- `forecast_semantic_alerts.csv`
- `golden_baseline_reconciliation.json`
"""

REPORT_MD.write_text(report, encoding="utf-8")

print("=" * 78)
print("PHASE 8.2.1B — GOLDEN BASELINE RECONCILIATION")
print("=" * 78)
print(f"Golden terminal: {baseline_html}")
print(f"Golden boosters: {len(boosters)}")
print(f"Golden Secret Lairs: {len(secret_lairs)}")
print(f"Candidate current sources: {len(source_inventory)}")
print(f"Candidate current rows: {len(current_records)}")
print(f"Matched rows: {len(match_rows)}")
print(f"Unmatched golden products: {len(unmatched_rows)}")
print(f"Duplicate current identities: {len(duplicate_rows)}")
print()
print("Product status:")
print(f"  PASS:   {status_counts.get('PASS', 0)}")
print(f"  REVIEW: {status_counts.get('REVIEW', 0)}")
print(f"  FAIL:   {status_counts.get('FAIL', 0)}")
print()
print(f"Forecast-semantic alerts: {len(semantic_alerts)}")

for alert_type, count in alert_counts.most_common():
    print(f"  {alert_type}: {count}")

print()
print(f"Report: {REPORT_MD}")
print("PHASE 8.2.1B RECONCILIATION: COMPLETE")
