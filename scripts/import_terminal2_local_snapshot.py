from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from terminal2.config import DB_FILE
from terminal2.db.local_snapshot_importer import (
    DEFAULT_MODEL_INPUT,
    import_local_snapshot,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import a local MTG model-input snapshot into "
            "the Terminal 2 SQLite database."
        )
    )

    parser.add_argument(
        "--observation-date",
        required=True,
        help="Snapshot date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--model-input",
        type=Path,
        default=DEFAULT_MODEL_INPUT,
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DB_FILE,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and map records without writing.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    try:
        result = import_local_snapshot(
            model_input_path=args.model_input,
            database_path=args.database,
            observation_date=args.observation_date,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print("TERMINAL 2 LOCAL SNAPSHOT IMPORT: FAILED")
        print(f"{type(exc).__name__}: {exc}")
        return 1

    print("=" * 72)
    print("Terminal 2 Local Snapshot Import")
    print("=" * 72)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'WRITE'}")
    print(f"Source: {result.source_file}")
    print(f"Observation date: {result.observation_date}")
    print(f"Source rows: {result.source_rows}")
    print(f"Valid rows: {result.valid_rows}")
    print(f"Matched rows: {result.matched_rows}")
    print(f"Rows written: {result.inserted_rows}")
    print("TERMINAL 2 LOCAL SNAPSHOT IMPORT: PASS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())