from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ACTIVE_REGISTRY_PATH = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "mtg_active_code_registry_v1.json"
)

ARCHIVE_ROOT = (
    ROOT
    / "archive"
    / "legacy"
    / "phase_8_2_3_one_time_patches"
)

AUDIT_PATH = (
    ROOT
    / "data"
    / "operations"
    / "mtg_standards_audit"
    / "active_code_cleanup_audit_v2.csv"
)

MANIFEST_PATH = (
    ARCHIVE_ROOT
    / "archive_manifest_v2.csv"
)

ACTIVE_SEARCH_SUFFIXES = {
    ".py",
    ".ps1",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
}

EXCLUDED_SEARCH_ROOTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "archive",
    "artifacts",
    "data",
    "docs",
    ".venv",
    "venv",
}

EXCLUDED_SEARCH_FILES = {
    "scripts/archive_obsolete_mtg_one_time_scripts.py",
}

EXPLICIT_CANDIDATES = {
    "scripts/patch_collector_case_exclusion_terms.py",
    "scripts/patch_collector_history_semantic_universe.py",
    "scripts/patch_collector_history_universe_policy.py",
    "scripts/patch_collector_universe_case_terms.py",
    "scripts/patch_dynamic_registry_tests.py",
    "scripts/patch_dynamic_registry_tests_safe.py",
    "scripts/patch_history_test_policy_fixture.py",
    "scripts/fix_dynamic_registry_test_root.py",
    "scripts/build_tier_1_forward_scenarios_v1_backup.py",
    "scripts/build_weekend_historical_purchase_screen_before_ledger_fix.py",
    "scripts/build_weekend_historical_purchase_screen_before_trusted_source_filter.py",
    "models/investment_features_before_universal_history_bridge.py",
    "tests/external_discovery/canonical_product_registry_before_dynamic_admission.py",
    "tests/external_discovery/canonical_registry_governance_before_dynamic_admission.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest().upper()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_registry() -> dict:
    return json.loads(
        ACTIVE_REGISTRY_PATH.read_text(
            encoding="utf-8-sig"
        )
    )


def discover_candidates(
    patterns: list[str],
) -> set[str]:
    candidates = set(EXPLICIT_CANDIDATES)

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        rel = relative(path)

        if any(
            fnmatch.fnmatch(rel, pattern)
            for pattern in patterns
        ):
            candidates.add(rel)

    return candidates


def active_search_files() -> list[Path]:
    results: list[Path] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(ROOT)
        rel_text = rel.as_posix()

        if rel_text in EXCLUDED_SEARCH_FILES:
            continue

        if any(
            part in EXCLUDED_SEARCH_ROOTS
            for part in rel.parts
        ):
            continue

        if path.suffix.lower() not in ACTIVE_SEARCH_SUFFIXES:
            continue

        results.append(path)

    return results


def reference_tokens(candidate: str) -> set[str]:
    path = Path(candidate)

    return {
        candidate,
        candidate.replace("/", "\\"),
        path.name,
        path.stem,
    }


def find_references(
    candidate: str,
    search_files: list[Path],
    candidate_set: set[str],
) -> list[str]:
    references: list[str] = []
    tokens = reference_tokens(candidate)

    for path in search_files:
        rel = relative(path)

        if rel == candidate:
            continue

        if rel in candidate_set:
            continue

        try:
            text = path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        except OSError:
            continue

        if any(token in text for token in tokens):
            references.append(rel)

    return sorted(set(references))


def archive_destination(source: Path) -> Path:
    safe_name = (
        relative(source)
        .replace("/", "__")
        + ".archived.txt"
    )

    destination = ARCHIVE_ROOT / safe_name

    if not destination.exists():
        return destination

    return ARCHIVE_ROOT / (
        safe_name
        + "."
        + sha256(source)[:12]
    )


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
    fields: list[str],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    registry = load_registry()

    authoritative = set(
        registry["authoritative_scripts"]
        + registry["authoritative_models"]
        + registry["authoritative_tests"]
    )

    candidates = discover_candidates(
        registry["approved_archive_patterns"]
    )

    candidates -= authoritative

    search_files = active_search_files()

    audit_rows: list[dict[str, str]] = []
    manifest_rows: list[dict[str, str]] = []

    ARCHIVE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    for candidate in sorted(candidates):
        source = ROOT / candidate

        if not source.exists():
            audit_rows.append({
                "candidate_path": candidate,
                "exists": "false",
                "reference_count": "0",
                "references": "",
                "action": "NOT_PRESENT",
            })
            continue

        references = find_references(
            candidate,
            search_files,
            candidates,
        )

        if references:
            audit_rows.append({
                "candidate_path": candidate,
                "exists": "true",
                "reference_count": str(
                    len(references)
                ),
                "references": "|".join(
                    references
                ),
                "action": "RETAIN_REFERENCED",
            })
            continue

        destination = archive_destination(
            source
        )

        source_hash = sha256(source)

        shutil.move(
            str(source),
            str(destination),
        )

        audit_rows.append({
            "candidate_path": candidate,
            "exists": "true",
            "reference_count": "0",
            "references": "",
            "action": "ARCHIVED",
        })

        manifest_rows.append({
            "archived_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "original_path": candidate,
            "archive_path": relative(
                destination
            ),
            "sha256": source_hash,
            "reason": (
                "Obsolete patch, backup, or "
                "one-time migration helper."
            ),
            "restoration_allowed": "true",
        })

    write_csv(
        AUDIT_PATH,
        audit_rows,
        [
            "candidate_path",
            "exists",
            "reference_count",
            "references",
            "action",
        ],
    )

    write_csv(
        MANIFEST_PATH,
        manifest_rows,
        [
            "archived_at_utc",
            "original_path",
            "archive_path",
            "sha256",
            "reason",
            "restoration_allowed",
        ],
    )

    print(
        "ACTIVE CODE CLEANUP AUDIT COMPLETE"
    )
    print(
        f"Candidates reviewed: "
        f"{len(candidates)}"
    )
    print(
        "Files archived: "
        f"{len(manifest_rows)}"
    )
    print(
        "Files retained due to references: "
        f"{sum(row['action'] == 'RETAIN_REFERENCED' for row in audit_rows)}"
    )


if __name__ == "__main__":
    main()