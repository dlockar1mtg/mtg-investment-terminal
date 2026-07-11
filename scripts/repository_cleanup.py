from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

GENERATED_PATHS = [
    "data/raw",
    "data/input",
    "data/investment",
    "data/market_inputs",
    "data/market_intelligence",
    "data/monte_carlo",
    "data/source_cache",
    "data/discovered",
    "data/market_database",
    "data/rolling_metrics",
    "data/market_signals",
    "data/dashboard",
    "data/analytics",
    "data/warehouse",
    "data/terminal2/archive_cache",
    "data/terminal2/extracted_archives",
    "data/terminal2/exports",
    "outputs",
]

TRACKED_REFERENCE_PATHS = [
    "data/product_master",
    "data/reference",
    "data/templates",
]

WORKSPACE_PATHS = [
    "workspace/raw",
    "workspace/cache",
    "workspace/history",
    "workspace/analytics",
    "workspace/market",
    "workspace/monte_carlo",
    "workspace/temp",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token)\s*=\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]{12,}"),
]


@dataclass
class Finding:
    level: str
    message: str


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def ensure_directories() -> None:
    for relative in WORKSPACE_PATHS:
        path = PROJECT_ROOT / relative
        path.mkdir(parents=True, exist_ok=True)


def write_workspace_readme() -> None:
    path = PROJECT_ROOT / "workspace" / "README.md"
    if path.exists():
        return
    path.write_text(
        "# Local Workspace\n\n"
        "This folder contains generated, downloaded, cached, and analytical runtime data.\n\n"
        "Its contents are intentionally excluded from Git. The project should recreate the "
        "required subdirectories automatically when workflows run.\n",
        encoding="utf-8",
    )


def audit_gitignore() -> list[Finding]:
    findings: list[Finding] = []
    required = [
        "data/raw/",
        "data/dashboard/",
        "data/analytics/",
        "data/warehouse/",
        "*.sqlite",
        "outputs/",
    ]
    path = PROJECT_ROOT / ".gitignore"
    if not path.exists():
        return [Finding("ERROR", ".gitignore is missing from the repository root.")]

    text = path.read_text(encoding="utf-8", errors="replace")
    for rule in required:
        if rule not in text:
            findings.append(Finding("ERROR", f"Required .gitignore rule is missing: {rule}"))
    return findings


def audit_ignored_paths() -> list[Finding]:
    findings: list[Finding] = []
    test_paths = [
        "data/terminal2/mtg_investment_terminal.sqlite",
        "data/dashboard",
        "data/analytics",
        "data/raw",
        "outputs",
    ]
    for relative in test_paths:
        result = run_git("check-ignore", "-q", relative)
        if result.returncode != 0:
            findings.append(Finding("ERROR", f"Git is not ignoring: {relative}"))
    return findings


def audit_untracked_data() -> list[Finding]:
    findings: list[Finding] = []
    result = run_git("status", "--short", "--untracked-files=all", "data")
    if result.returncode != 0:
        return [Finding("ERROR", result.stderr.strip() or "Could not inspect untracked data.")]

    allowed_prefixes = (
        "?? data/product_master/",
        "?? data/reference/",
        "?? data/templates/",
    )
    suspicious = [
        line for line in result.stdout.splitlines()
        if line.strip() and not line.startswith(allowed_prefixes)
    ]
    if suspicious:
        findings.append(
            Finding(
                "ERROR",
                f"{len(suspicious)} generated or unexpected data file(s) are still visible to Git. "
                "Run with --show-files to list them.",
            )
        )
    return findings


def audit_secrets() -> list[Finding]:
    findings: list[Finding] = []
    extensions = {".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".md"}
    excluded_parts = {".git", "workspace", "__pycache__", ".venv", "venv"}

    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if any(part in excluded_parts for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding("WARNING", f"Potential embedded credential in {path.relative_to(PROJECT_ROOT)}")
                )
                break
    return findings


def audit_large_files(max_mb: int = 25) -> list[Finding]:
    findings: list[Finding] = []
    threshold = max_mb * 1024 * 1024
    result = run_git("ls-files", "--others", "--exclude-standard")
    if result.returncode != 0:
        return findings

    for relative in result.stdout.splitlines():
        path = PROJECT_ROOT / relative
        if path.is_file() and path.stat().st_size > threshold:
            findings.append(
                Finding("WARNING", f"Large untracked file ({path.stat().st_size / 1024 / 1024:.1f} MB): {relative}")
            )
    return findings


def print_untracked_data() -> None:
    result = run_git("status", "--short", "--untracked-files=all", "data")
    print(result.stdout or "(No visible untracked files under data.)")


def apply_cleanup() -> None:
    ensure_directories()
    write_workspace_readme()
    print("Repository cleanup scaffolding created.")
    print("No existing runtime data was moved or deleted.")
    print("The updated .gitignore controls what Git tracks.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and prepare the MTG Investment Terminal repository.")
    parser.add_argument("--apply", action="store_true", help="Create workspace scaffolding.")
    parser.add_argument("--show-files", action="store_true", help="Show data files still visible to Git.")
    parser.add_argument("--max-file-mb", type=int, default=25, help="Warn above this untracked file size.")
    args = parser.parse_args()

    if args.apply:
        apply_cleanup()

    findings: list[Finding] = []
    findings.extend(audit_gitignore())
    findings.extend(audit_ignored_paths())
    findings.extend(audit_untracked_data())
    findings.extend(audit_secrets())
    findings.extend(audit_large_files(args.max_file_mb))

    if args.show_files:
        print("\nFiles visible to Git under data/:")
        print_untracked_data()

    print("\nRepository Cleanup Audit")
    print("=" * 60)

    if not findings:
        print("PASS: Repository is ready for the first commit.")
        return 0

    errors = 0
    for finding in findings:
        print(f"{finding.level}: {finding.message}")
        if finding.level == "ERROR":
            errors += 1

    if errors:
        print(f"\nFAILED: {errors} blocking issue(s) remain.")
        return 1

    print("\nPASS WITH WARNINGS: Review warnings before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
