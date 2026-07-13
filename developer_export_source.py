from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_REQUIRED_FILES = (
    "terminal2/warehouse_core/warehouse.py",
    "terminal2/warehouse_core/publisher.py",
    "terminal2/warehouse/dashboard_mart.py",
    "terminal2/market/exports.py",
    "terminal2_module2_run_all.py",
)


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def sanitize_branch_name(branch: str) -> str:
    value = branch.strip().replace("/", "-").replace("\\", "-")
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    return value.strip("-") or "unknown-branch"


def require_git_repository() -> None:
    result = run_git("rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise RuntimeError("This directory is not a Git repository.")

    repository_root = Path(result.stdout.strip()).resolve()
    if repository_root != PROJECT_ROOT.resolve():
        raise RuntimeError(
            f"Repository root mismatch. Expected {PROJECT_ROOT}, "
            f"but Git reported {repository_root}."
        )


def get_branch() -> str:
    result = run_git("branch", "--show-current")
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("Could not determine the current Git branch.")
    return result.stdout.strip()


def get_commit() -> str:
    result = run_git("rev-parse", "--short=8", "HEAD")
    if result.returncode != 0:
        raise RuntimeError("Could not determine the current Git commit.")
    return result.stdout.strip()


def get_status_lines() -> list[str]:
    result = run_git("status", "--porcelain")
    if result.returncode != 0:
        raise RuntimeError("Could not inspect the Git working tree.")
    return [line for line in result.stdout.splitlines() if line.strip()]


def verify_required_files(required_files: tuple[str, ...]) -> None:
    missing = [
        relative
        for relative in required_files
        if not (PROJECT_ROOT / relative).is_file()
    ]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            f"Required repository files are missing:\n{formatted}"
        )


def resolve_output_directory(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    downloads = Path.home() / "Downloads"
    return downloads if downloads.exists() else Path.cwd()


def export_source(
    output_directory: Path,
    *,
    allow_dirty: bool,
    required_files: tuple[str, ...],
) -> Path:
    require_git_repository()
    branch = get_branch()
    commit = get_commit()
    status_lines = get_status_lines()

    if status_lines and not allow_dirty:
        preview = "\n".join(f"  {line}" for line in status_lines[:20])
        raise RuntimeError(
            "The working tree is not clean. Commit, stash, or discard "
            f"changes before exporting.\n{preview}"
        )

    verify_required_files(required_files)
    output_directory.mkdir(parents=True, exist_ok=True)

    archive_path = output_directory / (
        "mtg-investment-terminal-"
        f"{sanitize_branch_name(branch)}-{commit}.zip"
    )

    result = run_git(
        "archive",
        "--format=zip",
        f"--output={archive_path}",
        "HEAD",
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "Git could not create the source archive."
        )

    if not archive_path.exists() or archive_path.stat().st_size == 0:
        raise RuntimeError("The source archive was not created correctly.")

    tracked = run_git("ls-files")
    tracked_count = len(
        [line for line in tracked.stdout.splitlines() if line.strip()]
    )

    print("MTG Investment Terminal source export")
    print("=" * 52)
    print(f"Branch: {branch}")
    print(f"Commit: {commit}")
    print(f"Working tree clean: {'No (allowed)' if status_lines else 'Yes'}")
    print(f"Required files: PASS ({len(required_files)})")
    print(f"Tracked files exported: {tracked_count}")
    print(f"Archive size: {archive_path.stat().st_size:,} bytes")
    print(f"Archive created: {archive_path}")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a verified ZIP of Git-tracked project files."
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for the ZIP. Defaults to Downloads.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Export committed HEAD even when local changes exist.",
    )
    args = parser.parse_args()

    try:
        export_source(
            resolve_output_directory(args.output_dir),
            allow_dirty=args.allow_dirty,
            required_files=DEFAULT_REQUIRED_FILES,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
