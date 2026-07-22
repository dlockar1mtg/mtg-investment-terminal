from __future__ import annotations

import json
import sys
from pathlib import Path


universal_root = Path(
    r"C:\Users\DevonLockard\InvestmentPlatform"
)

preview_path = Path(
    r"C:\Users\DevonLockard\mtg-investment-terminal"
    r"\data\staging\phase_10\universal_mapping"
    r"\asset_master_preview_2026-07-22.csv"
)

scripts_path = universal_root / "scripts"

if str(scripts_path) not in sys.path:
    sys.path.insert(
        0,
        str(scripts_path),
    )

from validate_contracts import validate_csv


report = validate_csv(
    preview_path,
    "asset_master",
)

print(
    json.dumps(
        report,
        indent=2,
        sort_keys=True,
    )
)

if not report["valid"]:
    raise SystemExit(1)

if report["record_count"] != 5239:
    raise SystemExit(
        "Unexpected Universal validation "
        f"record count: {report['record_count']}"
    )

print()
print(
    "UNIVERSAL ASSET_MASTER "
    "NATIVE VALIDATION: PASS"
)