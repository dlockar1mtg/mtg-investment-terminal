from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RECOVERY_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_8"
    / "secret_lair_history_recovery"
)

CANDIDATE = (
    RECOVERY_ROOT
    / "candidate_master_secret_lair_price_history.csv"
)

RECOVERY_MANIFEST = (
    RECOVERY_ROOT
    / "PHASE_8_2_1D_3_HISTORY_RECOVERY_MANIFEST.json"
)

VALIDATION = (
    RECOVERY_ROOT
    / "PHASE_8_2_1D_3_NO_LOSS_VALIDATION.json"
)

TARGET = (
    ROOT
    / "data"
    / "warehouse"
    / "current"
    / "secret_lair"
    / "master_secret_lair_price_history.csv"
)

BACKUP_ROOT = (
    ROOT
    / "data"
    / "operations"
    / "phase_8_2_1d_3_history_backups"
)


def certified(path: Path) -> bool:
    if not path.is_file():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("status") == "CERTIFIED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm",
        required=True,
        choices=["PROMOTE_CERTIFIED_HISTORY"],
    )
    args = parser.parse_args()

    if not CANDIDATE.is_file():
        raise FileNotFoundError(CANDIDATE)
    if not certified(RECOVERY_MANIFEST):
        raise RuntimeError("Recovery manifest is not certified.")
    if not certified(VALIDATION):
        raise RuntimeError("No-loss validation is not certified.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = BACKUP_ROOT / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)

    if TARGET.is_file():
        shutil.copy2(TARGET, backup_dir / TARGET.name)

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CANDIDATE, TARGET)

    record = {
        "status": "PROMOTED",
        "phase": "8.2.1D.3",
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": str(CANDIDATE),
        "target": str(TARGET),
        "backup": str(backup_dir),
    }
    (backup_dir / "promotion_record.json").write_text(
        json.dumps(record, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 78)
    print("PHASE 8.2.1D.3 — CERTIFIED HISTORY PROMOTION")
    print("=" * 78)
    print(f"Backup: {backup_dir}")
    print(f"Promoted: {CANDIDATE}")
    print(f"Target: {TARGET}")
    print("PHASE 8.2.1D.3 HISTORY PROMOTION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
