from __future__ import annotations

import importlib
import importlib.metadata
import json
import sqlite3
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from terminal2.db.module2_migration import migrate_module2


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PACKAGES = [
    "pandas",
    "numpy",
    "streamlit",
    "plotly",
    "requests",
    "python-dateutil",
    "py7zr",
]

PRODUCTION_MODULES = [
    "terminal2_run_all",
    "terminal2_module2_run_all",
    "terminal2_export",
    "terminal2.db.schema",
    "terminal2.db.module1_migration",
    "terminal2.db.module2_migration",
    "terminal2.db.loaders",
    "terminal2.features.price_features",
    "terminal2.analytics.scoring",
    "terminal2.warehouse.dashboard_mart",
    "terminal2.market.analytics.intelligence",
    "terminal2.market.analytics.health",
    "terminal2.market.exports",
    "terminal2.history",
    "terminal2.portfolio",
    "terminal2.forecast",
    "terminal2.intelligence",
    "terminal2.calibration",
    "terminal2.semantic",
    "terminal2.return_analytics",
    "terminal2.secret_lair",
]

REQUIRED_TABLES = {
    "products",
    "price_observations",
    "source_runs",
    "product_features",
    "investment_scores",
    "product_metadata",
    "supply_observations",
    "sales_observations",
    "market_intelligence",
    "market_health_history",
    "source_health_history",
}

REQUIRED_OUTPUT_ROOTS = [
    REPOSITORY_ROOT / "data",
    REPOSITORY_ROOT / "terminal2",
]


@dataclass(frozen=True)
class CertificationCheck:
    name: str
    status: str
    blocking: bool
    details: str


@dataclass(frozen=True)
class ProductionReadinessReport:
    generated_at_utc: str
    python_version: str
    overall_status: str
    checks: list[CertificationCheck]

    def to_dict(self) -> dict:
        return {
            "generated_at_utc": self.generated_at_utc,
            "python_version": self.python_version,
            "overall_status": self.overall_status,
            "checks": [
                asdict(check)
                for check in self.checks
            ],
        }


def _check_dependencies() -> CertificationCheck:
    versions = {}
    missing = []

    for package in REQUIRED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            missing.append(package)

    if missing:
        return CertificationCheck(
            name="runtime_dependencies",
            status="FAIL",
            blocking=True,
            details="Missing packages: " + ", ".join(missing),
        )

    details = ", ".join(
        f"{name}={version}"
        for name, version in sorted(versions.items())
    )

    return CertificationCheck(
        name="runtime_dependencies",
        status="PASS",
        blocking=True,
        details=details,
    )


def _check_imports() -> CertificationCheck:
    failures = []

    for module_name in PRODUCTION_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            failures.append(
                f"{module_name}: "
                f"{type(exc).__name__}: {exc}"
            )

    if failures:
        return CertificationCheck(
            name="production_imports",
            status="FAIL",
            blocking=True,
            details=" | ".join(failures),
        )

    return CertificationCheck(
        name="production_imports",
        status="PASS",
        blocking=True,
        details=(
            f"{len(PRODUCTION_MODULES)} production modules imported"
        ),
    )


def _check_removed_exports_contract() -> CertificationCheck:
    scripts = [
        REPOSITORY_ROOT / "terminal2_run_all.py",
        REPOSITORY_ROOT / "terminal2_module2_run_all.py",
        REPOSITORY_ROOT / "terminal2_export.py",
    ]

    violations = []

    for script in scripts:
        content = script.read_text(encoding="utf-8")

        if "terminal2.exports" in content:
            violations.append(
                f"{script.name}: terminal2.exports"
            )

        if "export_all()" in content:
            violations.append(
                f"{script.name}: export_all()"
            )

    if violations:
        return CertificationCheck(
            name="removed_export_contract",
            status="FAIL",
            blocking=True,
            details=", ".join(violations),
        )

    return CertificationCheck(
        name="removed_export_contract",
        status="PASS",
        blocking=True,
        details="No obsolete export package references",
    )


def _check_database() -> CertificationCheck:
    with tempfile.TemporaryDirectory() as temporary_directory:
        database_path = (
            Path(temporary_directory)
            / "mtg-readiness.sqlite"
        )

        migrate_module2(database_path)
        migrate_module2(database_path)

        connection = sqlite3.connect(database_path)

        try:
            tables = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name NOT LIKE 'sqlite_%'
                    """
                )
            }

            missing_tables = REQUIRED_TABLES - tables

            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            foreign_key_violations = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

        finally:
            connection.close()

    problems = []

    if missing_tables:
        problems.append(
            "missing tables: "
            + ", ".join(sorted(missing_tables))
        )

    if integrity != "ok":
        problems.append(
            f"integrity_check={integrity}"
        )

    if foreign_key_violations:
        problems.append(
            f"foreign_key_violations="
            f"{len(foreign_key_violations)}"
        )

    if problems:
        return CertificationCheck(
            name="database_integrity",
            status="FAIL",
            blocking=True,
            details=" | ".join(problems),
        )

    return CertificationCheck(
        name="database_integrity",
        status="PASS",
        blocking=True,
        details=(
            "Temporary migration completed twice; "
            "schema and integrity verified"
        ),
    )


def _check_output_roots() -> CertificationCheck:
    missing = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in REQUIRED_OUTPUT_ROOTS
        if not path.exists()
    ]

    if missing:
        return CertificationCheck(
            name="output_roots",
            status="FAIL",
            blocking=True,
            details="Missing roots: " + ", ".join(missing),
        )

    return CertificationCheck(
        name="output_roots",
        status="PASS",
        blocking=True,
        details="Required repository output roots exist",
    )


def _check_archive_dependency() -> CertificationCheck:
    scripts = [
        REPOSITORY_ROOT
        / "terminal2"
        / "sources"
        / "tcgcsv_archive.py",
        REPOSITORY_ROOT
        / "backfill_tcgcsv_monthly_history.py",
    ]

    violations = []

    for script in scripts:
        content = script.read_text(encoding="utf-8")

        for forbidden in [
            "7z.exe",
            "find_7z",
            'shutil.which("7z',
        ]:
            if forbidden in content:
                violations.append(
                    f"{script.name}: {forbidden}"
                )

    if violations:
        return CertificationCheck(
            name="python_native_archives",
            status="FAIL",
            blocking=True,
            details=", ".join(violations),
        )

    return CertificationCheck(
        name="python_native_archives",
        status="PASS",
        blocking=True,
        details="Active archive pipelines are Python-native",
    )


def _check_configuration_paths() -> CertificationCheck:
    import config
    import terminal2.config as terminal_config

    configured_paths = [
        Path(config.DATABASE_FILE),
        Path(config.MARKET_DATABASE_DIR),
        Path(terminal_config.DB_FILE),
        Path(terminal_config.ARCHIVE_CACHE_DIR),
        Path(terminal_config.ARCHIVE_EXTRACT_DIR),
    ]

    outside_repository = []

    for configured_path in configured_paths:
        resolved = configured_path.resolve()

        try:
            resolved.relative_to(REPOSITORY_ROOT)
        except ValueError:
            outside_repository.append(str(resolved))

    if outside_repository:
        return CertificationCheck(
            name="configuration_paths",
            status="FAIL",
            blocking=True,
            details=(
                "Configured paths outside repository: "
                + ", ".join(outside_repository)
            ),
        )

    return CertificationCheck(
        name="configuration_paths",
        status="PASS",
        blocking=True,
        details=(
            f"{len(configured_paths)} configured paths "
            "resolve inside the repository"
        ),
    )


def _check_network_timeouts() -> CertificationCheck:
    source_files = [
        REPOSITORY_ROOT / "collectors" / "common.py",
        REPOSITORY_ROOT
        / "collectors"
        / "scryfall_collector.py",
        REPOSITORY_ROOT
        / "collectors"
        / "tcgplayer_api_collector.py",
        REPOSITORY_ROOT
        / "terminal2"
        / "secret_lair"
        / "discovery"
        / "http_client.py",
        REPOSITORY_ROOT
        / "terminal2"
        / "secret_lair"
        / "master_database"
        / "http_client.py",
        REPOSITORY_ROOT
        / "terminal2"
        / "sources"
        / "tcgcsv_archive.py",
        REPOSITORY_ROOT
        / "backfill_tcgcsv_monthly_history.py",
    ]

    missing_files = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in source_files
        if not path.exists()
    ]

    if missing_files:
        return CertificationCheck(
            name="network_timeouts",
            status="FAIL",
            blocking=True,
            details=(
                "Missing source modules: "
                + ", ".join(missing_files)
            ),
        )

    violations = []

    for source_file in source_files:
        content = source_file.read_text(
            encoding="utf-8"
        )

        network_calls = (
            "requests.get(" in content
            or "requests.post(" in content
            or "requests.request(" in content
            or "urlopen(" in content
        )

        if network_calls and "timeout" not in content:
            violations.append(
                str(source_file.relative_to(REPOSITORY_ROOT))
            )

    if violations:
        return CertificationCheck(
            name="network_timeouts",
            status="FAIL",
            blocking=True,
            details=(
                "Network modules without timeout controls: "
                + ", ".join(violations)
            ),
        )

    return CertificationCheck(
        name="network_timeouts",
        status="PASS",
        blocking=True,
        details=(
            f"{len(source_files)} network source modules "
            "include explicit timeout controls"
        ),
    )



def run_production_readiness() -> ProductionReadinessReport:
    checks = [
        _check_dependencies(),
        _check_imports(),
        _check_removed_exports_contract(),
        _check_database(),
        _check_output_roots(),
        _check_configuration_paths(),
        _check_network_timeouts(),
        _check_archive_dependency(),
    ]

    blocking_failures = [
        check
        for check in checks
        if check.blocking and check.status != "PASS"
    ]

    overall_status = (
        "PASS"
        if not blocking_failures
        else "FAIL"
    )

    return ProductionReadinessReport(
        generated_at_utc=datetime.now(
            timezone.utc
        ).isoformat(),
        python_version=sys.version,
        overall_status=overall_status,
        checks=checks,
    )


def write_report(
    report: ProductionReadinessReport,
    output_directory: Path,
) -> tuple[Path, Path]:
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        output_directory
        / "phase_10_4_production_readiness.json"
    )

    markdown_path = (
        output_directory
        / "phase_10_4_production_readiness.md"
    )

    json_path.write_text(
        json.dumps(
            report.to_dict(),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Phase 10.4 Production-Readiness Report",
        "",
        f"- Generated: `{report.generated_at_utc}`",
        f"- Overall status: **{report.overall_status}**",
        "",
        "## Certification checks",
        "",
    ]

    for check in report.checks:
        lines.extend(
            [
                f"### {check.name}",
                "",
                f"- Status: **{check.status}**",
                f"- Blocking: `{check.blocking}`",
                f"- Details: {check.details}",
                "",
            ]
        )

    markdown_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return json_path, markdown_path