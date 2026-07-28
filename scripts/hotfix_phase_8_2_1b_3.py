from __future__ import annotations

import ast
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PRODUCER = (
    ROOT
    / "terminal2"
    / "market_sources"
    / "collector_box_evaluation.py"
)

PAYLOAD_PRODUCER = (
    ROOT
    / "scripts"
    / "phase_8_2_1b_3_payload"
    / "collector_box_evaluation.py"
)

HOSTED = (
    ROOT
    / "scripts"
    / "build_mtg_hosted_uip_delivery.py"
)

BACKUP = (
    ROOT
    / "data"
    / "operations"
    / "phase_8_2_1b_3_hotfix_backups"
    / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
)


def backup(path: Path) -> None:
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def replace_exact(
    text: str,
    old: str,
    new: str,
    expected: int,
    label: str,
) -> str:
    count = text.count(old)

    if count != expected:
        raise RuntimeError(
            f"{label}: expected {expected} occurrence(s), "
            f"found {count}"
        )

    return text.replace(old, new)


for path in (PRODUCER, HOSTED):
    backup(path)

producer_text = PRODUCER.read_text(
    encoding="utf-8",
)

producer_text = replace_exact(
    producer_text,
    '            forecast_eligible = "YES"\n'
    '            consumption_state = "NATIVE_RANGE_ONLY"',
    '            # A native Monte Carlo range is a valuation range, not a\n'
    '            # certified horizon forecast.\n'
    '            forecast_eligible = "NO"\n'
    '            consumption_state = "NATIVE_RANGE_ONLY"',
    1,
    "native-range forecast eligibility",
)

producer_text = replace_exact(
    producer_text,
    '            "forecast_eligible": forecast_eligible,\n'
    '            "native_forecast_low_usd": _money(native_low),',
    '            "forecast_eligible": forecast_eligible,\n'
    '            "native_range_eligible": (\n'
    '                "YES" if native_ready else "NO"\n'
    '            ),\n'
    '            "native_forecast_low_usd": _money(native_low),',
    1,
    "native-range eligibility field",
)

PRODUCER.write_text(
    producer_text,
    encoding="utf-8",
)

PAYLOAD_PRODUCER.parent.mkdir(
    parents=True,
    exist_ok=True,
)

shutil.copy2(
    PRODUCER,
    PAYLOAD_PRODUCER,
)

hosted_text = HOSTED.read_text(
    encoding="utf-8",
)

malformed = " if horizon_certified else ,"
corrected = ' if horizon_certified else "",'

malformed_count = hosted_text.count(malformed)

if malformed_count != 9:
    raise RuntimeError(
        "hosted horizon syntax: expected 9 malformed expressions, "
        f"found {malformed_count}"
    )

hosted_text = hosted_text.replace(
    malformed,
    corrected,
)

HOSTED.write_text(
    hosted_text,
    encoding="utf-8",
)

for path in (
    PRODUCER,
    PAYLOAD_PRODUCER,
    HOSTED,
):
    ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )

print("=" * 78)
print("PHASE 8.2.1B.3 — IMPLEMENTATION HOTFIX")
print("=" * 78)
print("PASS | native range no longer marked as horizon-forecast eligible")
print("PASS | native_range_eligible field added")
print("PASS | nine hosted-delivery syntax defects repaired")
print("PASS | producer payload synchronized")
print("PASS | all modified Python files parse successfully")
print(f"Backup: {BACKUP}")
print("PHASE 8.2.1B.3 HOTFIX: PASS")
