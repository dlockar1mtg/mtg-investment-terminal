from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BLOCKED_PATTERNS = (
    ".sqlite",
    ".sqlite3",
    ".db",
    ".7z",
    ".zip",
    "data/raw/",
    "data/dashboard/",
    "data/analytics/",
    "data/warehouse/",
    "outputs/",
)

MAX_STAGED_BYTES = 25 * 1024 * 1024


def git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def main():
    staged = git("diff", "--cached", "--name-only")
    if staged.returncode != 0:
        print(staged.stderr)
        return 1

    files = [line.strip().replace("\\", "/") for line in staged.stdout.splitlines() if line.strip()]
    problems = []

    for relative in files:
        lower = relative.lower()
        if any(pattern in lower for pattern in BLOCKED_PATTERNS):
            problems.append(f"Blocked generated or local file is staged: {relative}")
            continue

        path = ROOT / relative
        if path.exists() and path.is_file() and path.stat().st_size > MAX_STAGED_BYTES:
            problems.append(
                f"Large staged file ({path.stat().st_size / 1024 / 1024:.1f} MB): {relative}"
            )

    if problems:
        print("Pre-commit audit failed:")
        for problem in problems:
            print(f"  - {problem}")
        print("\nRemove files from staging with: git restore --staged <path>")
        return 1

    print(f"Pre-commit audit passed. Staged files: {len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
