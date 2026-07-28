from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODEL_INPUT = ROOT / "data" / "product_master" / "product_master_model_input.csv"
GOVERNED = ROOT / "data" / "warehouse" / "current" / "governed_terminal" / "forecasts.csv"
TERMINAL = ROOT / "data" / "operations" / "mtg_terminal_delivery" / "latest" / "forecasts.csv"
UIP = ROOT / "data" / "operations" / "mtg_uip_delivery" / "latest" / "forecasts.csv"
OUTPUT = ROOT / "docs" / "phase_8" / "mtg_intelligence_recovery" / "forecast_semantic_repair"

TARGET = "TCGCSV-22876-489207"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return None if math.isnan(value) else value


def sid(row: dict[str, str]) -> str:
    for key in ("source_product_id", "legacy_source_product_id", "investment_product_id", "canonical_product_id", "asset_id"):
        value = str(row.get(key, "") or "").strip()
        if value:
            return value.split(":")[-1] if value.startswith("MTG:") else value
    return ""


def target_row(path: Path) -> dict[str, str]:
    matches = [row for row in rows(path) if sid(row) == TARGET]
    if len(matches) != 1:
        raise AssertionError(f"{path}: expected one target row, found {len(matches)}")
    return matches[0]


model = target_row(MODEL_INPUT)
governed = target_row(GOVERNED)
terminal = target_row(TERMINAL)
uip = target_row(UIP)

expected_current = number(model["current_price"])
expected_low = number(model["mc_p05"])
expected_base = number(model["mc_median"])
expected_high = number(model["mc_p95"])

checks = {
    "model_values_present": all(value is not None for value in (expected_current, expected_low, expected_base, expected_high)),
    "governed_current_matches_model": abs(number(governed["selected_reference_price"]) - expected_current) <= 0.01,
    "terminal_current_matches_model": abs(number(terminal["selected_reference_price"]) - expected_current) <= 0.01,
    "uip_current_matches_model": abs(number(uip["current_market_value_usd"]) - expected_current) <= 0.01,
    "uip_native_low_matches_model": abs(number(uip["native_forecast_low_usd"]) - expected_low) <= 0.01,
    "uip_native_base_matches_model": abs(number(uip["native_forecast_base_usd"]) - expected_base) <= 0.01,
    "uip_native_high_matches_model": abs(number(uip["native_forecast_high_usd"]) - expected_high) <= 0.01,
    "governed_method_native": governed["forecast_method"] == "NATIVE_MONTE_CARLO_RANGE",
    "terminal_method_native": terminal["forecast_method"] == "NATIVE_MONTE_CARLO_RANGE",
    "uip_method_native": uip["forecast_method"] == "NATIVE_MONTE_CARLO_RANGE",
    "bad_825_removed": abs(number(uip["current_market_value_usd"]) - 825.0) > 1.0,
    "bad_891_removed": str(governed.get("one_year_base_usd", "")).strip() == "",
    "horizon_fields_suppressed": all(
        str(uip.get(key, "")).strip() == ""
        for key in (
            "one_year_downside_usd", "one_year_base_usd", "one_year_upside_usd",
            "three_year_downside_usd", "three_year_base_usd", "three_year_upside_usd",
            "five_year_downside_usd", "five_year_base_usd", "five_year_upside_usd",
        )
    ),
    "native_interval_ordered": expected_low <= expected_base <= expected_high,
}

status = "CERTIFIED" if all(checks.values()) else "FAILED"
OUTPUT.mkdir(parents=True, exist_ok=True)

result = {
    "status": status,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "target_product": TARGET,
    "expected": {
        "current_market_value_usd": expected_current,
        "native_forecast_low_usd": expected_low,
        "native_forecast_base_usd": expected_base,
        "native_forecast_high_usd": expected_high,
    },
    "checks": checks,
}

(OUTPUT / "PHASE_8_2_1B_2_CERTIFICATION.json").write_text(
    json.dumps(result, indent=2) + "\n",
    encoding="utf-8",
)

lines = [
    "# Phase 8.2.1B.2 — Forecast Semantic Repair Certification",
    "",
    f"**Status:** {status}",
    "",
    f"- Current value: ${expected_current:,.2f}",
    f"- Native low: ${expected_low:,.2f}",
    f"- Native base: ${expected_base:,.2f}",
    f"- Native high: ${expected_high:,.2f}",
    "",
    "## Checks",
    "",
]
lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
(OUTPUT / "PHASE_8_2_1B_2_FORECAST_SEMANTIC_REPAIR.md").write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
)

print("=" * 78)
print("PHASE 8.2.1B.2 — FORECAST SEMANTIC CERTIFICATION")
print("=" * 78)
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} | {name}")
print(f"PHASE 8.2.1B.2 CERTIFICATION: {status}")
raise SystemExit(0 if status == "CERTIFIED" else 1)
