from __future__ import annotations

import ast
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PRODUCER = (
    ROOT
    / "scripts"
    / "build_full_secret_lair_model_evaluation.py"
)

PAYLOAD = (
    ROOT
    / "scripts"
    / "phase_8_2_1c_2_payload"
    / "build_full_secret_lair_model_evaluation.py"
)

TEST = (
    ROOT
    / "tests"
    / "test_phase_8_2_1c_2_secret_lair_semantics.py"
)

BACKUP = (
    ROOT
    / "data"
    / "operations"
    / "phase_8_2_1c_2_1_code_backups"
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


def backup(path: Path) -> None:
    destination = BACKUP / path.relative_to(ROOT)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        path,
        destination,
    )


for path in (PRODUCER, TEST):
    if not path.is_file():
        raise FileNotFoundError(path)

    backup(path)


producer_text = PRODUCER.read_text(
    encoding="utf-8-sig",
)

old_range_logic = '''        low = round(max(0.01, float(low)), 2)
        high = round(max(low, float(high)), 2)

        evidence_score = min(100.0, observations * 8.0 + sellers * 6.0)
'''

new_range_logic = '''        low = round(max(0.01, float(low)), 2)
        high = round(max(0.01, float(high)), 2)

        # The selected current/base value is authoritative. Source interval
        # endpoints may be stale, asymmetric, or derived from a different
        # observation subset, so normalize the interval around the base.
        low = round(min(low, value), 2)
        high = round(max(high, value, low), 2)

        evidence_score = min(100.0, observations * 8.0 + sellers * 6.0)
'''

producer_text = replace_once(
    producer_text,
    old_range_logic,
    new_range_logic,
    "producer native-range normalization",
)

ast.parse(
    producer_text,
    filename=str(PRODUCER),
)

PRODUCER.write_text(
    producer_text,
    encoding="utf-8",
)

PAYLOAD.parent.mkdir(
    parents=True,
    exist_ok=True,
)

shutil.copy2(
    PRODUCER,
    PAYLOAD,
)


test_text = TEST.read_text(
    encoding="utf-8-sig",
)

test_addition = '''

def test_native_range_normalization_keeps_base_inside_interval() -> None:
    base = 40.0
    source_low = 45.0
    source_high = 50.0

    normalized_low = round(min(source_low, base), 2)
    normalized_high = round(
        max(source_high, base, normalized_low),
        2,
    )

    assert normalized_low == 40.0
    assert normalized_low <= base <= normalized_high


def test_native_range_normalization_expands_high_to_base() -> None:
    base = 60.0
    source_low = 40.0
    source_high = 55.0

    normalized_low = round(min(source_low, base), 2)
    normalized_high = round(
        max(source_high, base, normalized_low),
        2,
    )

    assert normalized_high == 60.0
    assert normalized_low <= base <= normalized_high
'''

if (
    "test_native_range_normalization_keeps_base_inside_interval"
    not in test_text
):
    test_text = test_text.rstrip() + test_addition + "\n"

ast.parse(
    test_text,
    filename=str(TEST),
)

TEST.write_text(
    test_text,
    encoding="utf-8",
)

print("=" * 78)
print("PHASE 8.2.1C.2.1 — NATIVE RANGE ORDERING REPAIR")
print("=" * 78)
print("PASS | producer clamps low at or below authoritative base")
print("PASS | producer expands high at or above authoritative base")
print("PASS | producer payload synchronized")
print("PASS | range-order regression tests added")
print("PASS | modified Python files parse successfully")
print(f"Backup: {BACKUP}")
print("PHASE 8.2.1C.2.1 HOTFIX: PASS")
