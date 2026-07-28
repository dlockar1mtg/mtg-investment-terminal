from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODEL_INPUT = ROOT / "data" / "product_master" / "product_master_model_input.csv"

GOVERNED_ROOT = ROOT / "data" / "warehouse" / "current" / "governed_terminal"
TERMINAL_ROOT = ROOT / "data" / "operations" / "mtg_terminal_delivery" / "latest"
UIP_ROOT = ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest"
EVIDENCE_ROOT = ROOT / "docs" / "phase_8" / "mtg_intelligence_recovery" / "forecast_semantic_repair"

TARGET_FILES = (
    GOVERNED_ROOT / "dashboard.csv",
    GOVERNED_ROOT / "forecasts.csv",
    GOVERNED_ROOT / "rankings.csv",
    GOVERNED_ROOT / "recommendations.csv",
    GOVERNED_ROOT / "universal_mtg_consumption_interface.csv",
    TERMINAL_ROOT / "dashboard.csv",
    TERMINAL_ROOT / "forecasts.csv",
    TERMINAL_ROOT / "rankings.csv",
    TERMINAL_ROOT / "recommendations.csv",
    TERMINAL_ROOT / "universal_mtg_consumption_interface.csv",
    UIP_ROOT / "forecasts.csv",
    UIP_ROOT / "recommendations.csv",
)

COLLECTOR_TOKEN = "COLLECTOR_BOOSTER_BOX"
FORECAST_METHOD = "NATIVE_MONTE_CARLO_RANGE"
FORECAST_STATUS = "NATIVE_RANGE_READY"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty dataset: {path}")

    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def text(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    raw = text(value).replace("$", "").replace(",", "")
    if not raw:
        return None
    try:
        result = float(raw)
    except ValueError:
        return None
    return None if math.isnan(result) else result


def money(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def source_id(row: dict[str, Any]) -> str:
    for key in (
        "source_product_id",
        "legacy_source_product_id",
        "investment_product_id",
        "canonical_product_id",
        "asset_id",
    ):
        value = text(row.get(key))
        if not value:
            continue
        if value.startswith("MTG:"):
            value = value.split(":")[-1]
        return value
    return ""


def is_collector(row: dict[str, Any]) -> bool:
    joined = " ".join(
        text(row.get(key)).upper()
        for key in (
            "product_class",
            "asset_subclass",
            "lane",
            "canonical_product_id",
            "asset_id",
        )
    )
    return COLLECTOR_TOKEN in joined


def model_index() -> dict[str, dict[str, str]]:
    rows = read_csv(MODEL_INPUT)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        sid = text(row.get("investment_product_id"))
        if sid:
            result[sid] = row
    return result


def native_values(model: dict[str, str]) -> dict[str, str]:
    current = (
        number(model.get("current_price"))
        or number(model.get("market_price"))
        or number(model.get("current_price_history"))
        or number(model.get("current_price_db"))
    )
    low = number(model.get("mc_p05"))
    base = number(model.get("mc_median")) or number(model.get("mc_expected_value"))
    high = number(model.get("mc_p95"))

    return {
        "current": money(current),
        "low": money(low),
        "base": money(base),
        "high": money(high),
    }


def clear_horizons(row: dict[str, Any]) -> None:
    for key in (
        "one_year_downside_usd",
        "one_year_base_usd",
        "one_year_upside_usd",
        "three_year_downside_usd",
        "three_year_base_usd",
        "three_year_upside_usd",
        "five_year_downside_usd",
        "five_year_base_usd",
        "five_year_upside_usd",
        "1y_downside_usd",
        "1y_base_usd",
        "1y_upside_usd",
        "3y_downside_usd",
        "3y_base_usd",
        "3y_upside_usd",
        "5y_downside_usd",
        "5y_base_usd",
        "5y_upside_usd",
        "expected_return",
        "forecast_horizon_months",
        "guarded_rank_score",
        "guarded_rank",
    ):
        if key in row:
            row[key] = ""


def repair_governed_row(row: dict[str, Any], values: dict[str, str]) -> None:
    row["selected_reference_price"] = values["current"]
    row["forecast_method"] = FORECAST_METHOD
    row["legacy_forecast_status"] = FORECAST_STATUS
    row["forecast_consumption_state"] = "NATIVE_RANGE_ONLY"
    row["governed_forecast_eligible"] = "TRUE"
    row["legacy_forecast_eligible"] = "YES"
    row["native_forecast_low_usd"] = values["low"]
    row["native_forecast_base_usd"] = values["base"]
    row["native_forecast_high_usd"] = values["high"]
    row["horizon_forecast_status"] = "SUPPRESSED_UNTIL_HORIZON_MODEL_CERTIFIED"
    clear_horizons(row)


def repair_uip_forecast(row: dict[str, Any], values: dict[str, str]) -> None:
    row["current_market_value_usd"] = values["current"]
    row["forecast_method"] = FORECAST_METHOD
    row["forecast_status"] = FORECAST_STATUS
    row["forecast_eligible"] = "YES"
    row["native_forecast_low_usd"] = values["low"]
    row["native_forecast_base_usd"] = values["base"]
    row["native_forecast_high_usd"] = values["high"]
    row["horizon_forecast_status"] = "SUPPRESSED_UNTIL_HORIZON_MODEL_CERTIFIED"
    clear_horizons(row)


def repair_uip_recommendation(row: dict[str, Any]) -> None:
    row["recommendation_eligible"] = "NO"
    row["recommendation_action"] = "HOLD_REVIEW"
    row["recommendation_status"] = "AWAITING_HORIZON_FORECAST_CERTIFICATION"
    row["recommendation_rationale"] = (
        "Native Monte Carlo valuation range is retained; directional recommendation "
        "is withheld until horizon-specific forecasts are certified."
    )


def backup_files(paths: tuple[Path, ...], backup_root: Path) -> None:
    for path in paths:
        if not path.is_file():
            continue
        destination = backup_root / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    models = model_index()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = ROOT / "data" / "operations" / "phase_8_2_1b_2_backups" / timestamp

    if args.apply:
        backup_files(TARGET_FILES, backup_root)

    changes: list[dict[str, Any]] = []
    missing_models: list[dict[str, str]] = []

    for path in TARGET_FILES:
        if not path.is_file():
            continue

        rows = read_csv(path)
        changed = 0

        for row in rows:
            if not is_collector(row):
                continue

            sid = source_id(row)
            model = models.get(sid)

            if model is None:
                missing_models.append({"path": str(path.relative_to(ROOT)), "source_product_id": sid})
                continue

            values = native_values(model)
            if not all((values["current"], values["low"], values["base"], values["high"])):
                missing_models.append({"path": str(path.relative_to(ROOT)), "source_product_id": sid})
                continue

            if path.parent == UIP_ROOT and path.name == "forecasts.csv":
                repair_uip_forecast(row, values)
            elif path.parent == UIP_ROOT and path.name == "recommendations.csv":
                repair_uip_recommendation(row)
            else:
                repair_governed_row(row, values)

            changed += 1

        changes.append(
            {
                "path": str(path.relative_to(ROOT)),
                "rows": len(rows),
                "collector_rows_repaired": changed,
            }
        )

        if args.apply and changed:
            write_csv(path, rows)

    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "APPLIED" if args.apply else "DRY_RUN",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "forecast_method": FORECAST_METHOD,
        "changes": changes,
        "missing_model_rows": missing_models,
        "backup_root": str(backup_root) if args.apply else "",
    }
    (EVIDENCE_ROOT / "phase_8_2_1b_2_repair_result.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 78)
    print("PHASE 8.2.1B.2 — FORECAST SEMANTIC REPAIR")
    print("=" * 78)
    print(f"Mode: {result['status']}")
    for item in changes:
        print(f"  {item['collector_rows_repaired']:>3} repaired | {item['path']}")
    print(f"Missing model rows: {len(missing_models)}")
    if args.apply:
        print(f"Backup: {backup_root}")
    print("PHASE 8.2.1B.2 REPAIR: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
