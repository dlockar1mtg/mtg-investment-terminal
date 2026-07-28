from __future__ import annotations

import ast
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

HOSTED = (
    ROOT
    / "scripts"
    / "build_mtg_hosted_uip_delivery.py"
)

UNIFIED = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "unified_mtg_intelligence"
    / "unified_mtg_intelligence_interface.csv"
)

BACKUP = (
    ROOT
    / "data"
    / "operations"
    / "phase_8_2_1b_3_hosted_source_backups"
    / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
)


def replace_once(
    text: str,
    old: str,
    new: str,
    label: str,
) -> str:
    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one occurrence, "
            f"found {count}"
        )

    return text.replace(old, new, 1)


if not UNIFIED.is_file():
    raise FileNotFoundError(
        f"Certified unified interface not found: {UNIFIED}"
    )

backup_path = BACKUP / HOSTED.relative_to(ROOT)
backup_path.parent.mkdir(
    parents=True,
    exist_ok=True,
)

shutil.copy2(
    HOSTED,
    backup_path,
)

text = HOSTED.read_text(
    encoding="utf-8-sig",
)

old_constant = '''BASELINE = ROOT / "data" / "reference" / "phase_11" / "mtg_hosted_baseline"
DEFAULT_OUTPUT = ROOT / "data" / "operations" / "mtg_uip_delivery"
'''

new_constant = '''BASELINE = ROOT / "data" / "reference" / "phase_11" / "mtg_hosted_baseline"
UNIFIED_INTERFACE = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "unified_mtg_intelligence"
    / "unified_mtg_intelligence_interface.csv"
)
DEFAULT_OUTPUT = ROOT / "data" / "operations" / "mtg_uip_delivery"
'''

text = replace_once(
    text,
    old_constant,
    new_constant,
    "unified interface constant",
)

old_build_start = '''    lane_counts: dict[str, int] = {}

    for key, (registry_path, evaluation_path) in FILES.items():
        lane = LANE_NAMES[key]
        registry = read_csv(registry_path)
        evaluation = read_csv(evaluation_path)
        lane_counts[lane] = len(registry)

        evaluation_by_id = {source_id(row): row for row in evaluation if source_id(row)}
'''

new_build_start = '''    lane_counts: dict[str, int] = {}

    unified_rows = read_csv(UNIFIED_INTERFACE)

    if len(unified_rows) != 1141:
        raise RuntimeError(
            "Unified intelligence interface must contain 1,141 rows; "
            f"found {len(unified_rows)}"
        )

    unified_ids = {
        first(row, "universal_mtg_product_id")
        for row in unified_rows
        if first(row, "universal_mtg_product_id")
    }

    if len(unified_ids) != len(unified_rows):
        raise RuntimeError(
            "Unified intelligence interface contains duplicate or "
            "missing universal product IDs."
        )

    for key, (registry_path, _legacy_evaluation_path) in FILES.items():
        lane = LANE_NAMES[key]
        registry = read_csv(registry_path)

        evaluation = [
            row
            for row in unified_rows
            if first(row, "lane") == lane
        ]

        lane_counts[lane] = len(registry)

        evaluation_by_id = {
            source_id(row): row
            for row in evaluation
            if source_id(row)
        }
'''

text = replace_once(
    text,
    old_build_start,
    new_build_start,
    "hosted unified-source initialization",
)

old_eligible = '''            eligible = recommendation_action not in {"", "NO_ACTION", "WATCH"}
'''

new_eligible = '''            eligible = (
                normalize_bool(
                    first(
                        evaluation_row,
                        "recommendation_eligible",
                        default="NO",
                    )
                )
                == "YES"
            )
'''

text = replace_once(
    text,
    old_eligible,
    new_eligible,
    "recommendation eligibility mapping",
)

old_status = '''    platform_rows = [{
        "platform": "MTG",
'''

new_status = '''    aftermath_rows = [
        row
        for row in forecast_rows
        if row["source_product_id"] == "TCGCSV-22876-489207"
    ]

    if len(aftermath_rows) != 1:
        raise RuntimeError(
            "Expected exactly one hosted Aftermath forecast row."
        )

    aftermath = aftermath_rows[0]

    if aftermath["current_market_value_usd"] != "227.18":
        raise RuntimeError(
            "Hosted Aftermath current value regressed: "
            f"{aftermath['current_market_value_usd']}"
        )

    if aftermath["forecast_method"] != "NATIVE_MONTE_CARLO_RANGE":
        raise RuntimeError(
            "Hosted Aftermath forecast method regressed: "
            f"{aftermath['forecast_method']}"
        )

    if aftermath["native_forecast_base_usd"] != "340.58":
        raise RuntimeError(
            "Hosted Aftermath native forecast base regressed: "
            f"{aftermath['native_forecast_base_usd']}"
        )

    if any(
        aftermath[field]
        for field in (
            "one_year_base_usd",
            "three_year_base_usd",
            "five_year_base_usd",
        )
    ):
        raise RuntimeError(
            "Hosted Aftermath contains uncertified horizon values."
        )

    platform_rows = [{
        "platform": "MTG",
'''

text = replace_once(
    text,
    old_status,
    new_status,
    "hosted Aftermath fail-closed validation",
)

ast.parse(
    text,
    filename=str(HOSTED),
)

HOSTED.write_text(
    text,
    encoding="utf-8",
)

print("=" * 78)
print("PHASE 8.2.1B.3.1 — HOSTED DELIVERY SOURCE REPAIR")
print("=" * 78)
print("PASS | hosted delivery now consumes certified unified intelligence")
print("PASS | legacy evaluation files removed from active value mapping")
print("PASS | recommendation eligibility comes from unified intelligence")
print("PASS | Aftermath fail-closed regression checks installed")
print("PASS | modified hosted builder parses successfully")
print(f"Backup: {BACKUP}")
print("PHASE 8.2.1B.3.1 HOTFIX: PASS")
