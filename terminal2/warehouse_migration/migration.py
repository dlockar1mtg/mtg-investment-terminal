from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from terminal2.warehouse_core import (
    DashboardPublisher,
    DatasetDefinition,
    Warehouse,
    get_warehouse_config,
)

from .catalog import MigrationCandidate, discover_legacy_datasets


@dataclass(frozen=True)
class MigrationResult:
    dataset_name: str
    category: str
    source_kind: str
    source_path: str
    warehouse_path: str
    snapshot_path: str
    row_count: int
    column_count: int
    source_modified_at_utc: str
    migrated_at_utc: str
    refresh_id: str
    status: str
    warning: str = ""

    def to_record(self) -> dict:
        return asdict(self)


class WarehouseMigration:
    def __init__(
        self,
        *,
        project_root: Path | None = None,
        warehouse: Warehouse | None = None,
    ):
        if warehouse is None:
            warehouse = Warehouse(
                config=get_warehouse_config(project_root)
            )
        self.warehouse = warehouse
        self.project_root = warehouse.config.project_root
        self.publisher = DashboardPublisher(warehouse)

    def migrate(
        self,
        *,
        create_snapshots: bool = True,
        include_analytics_current: bool = True,
        continue_on_error: bool = False,
    ) -> dict:
        candidates, warnings = discover_legacy_datasets(
            self.project_root,
            include_analytics_current=include_analytics_current,
        )

        run = self.warehouse.refresh.start(
            "Terminal 2.5.1c warehouse migration"
        )
        results: list[MigrationResult] = []
        errors: list[str] = []

        try:
            for candidate in candidates:
                try:
                    results.append(
                        self._migrate_candidate(
                            candidate,
                            refresh_id=run.refresh_id,
                            create_snapshots=create_snapshots,
                        )
                    )
                except Exception as exc:
                    message = (
                        f"{candidate.source_relative_path}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    errors.append(message)
                    if not continue_on_error:
                        raise

            status = "partial" if errors else "success"
            self.warehouse.refresh.finish(
                status=status,
                datasets_published=len(results),
                warnings=len(warnings),
                errors=len(errors),
            )
        except Exception as exc:
            active = self.warehouse.refresh.active_run
            if active and active.status == "running":
                self.warehouse.refresh.fail(exc)
            raise

        return self._write_reports(
            results=results,
            warnings=warnings,
            errors=errors,
            refresh_id=run.refresh_id,
            status=status,
        )

    def _migrate_candidate(
        self,
        candidate: MigrationCandidate,
        *,
        refresh_id: str,
        create_snapshots: bool,
    ) -> MigrationResult:
        dataframe = pd.read_csv(candidate.source_path)
        definition = DatasetDefinition(
            name=candidate.dataset_name,
            category=candidate.category,
            module="terminal2.warehouse_migration",
            description=(
                "Migrated from "
                f"{candidate.source_relative_path}."
            ),
            expected_columns=tuple(
                str(column) for column in dataframe.columns
            ),
            snapshot=candidate.snapshot and create_snapshots,
        )

        published = self.publisher.publish(
            dataframe,
            definition,
            refresh_id=refresh_id,
            create_snapshot=candidate.snapshot and create_snapshots,
        )

        return MigrationResult(
            dataset_name=published.dataset_name,
            category=published.category,
            source_kind=candidate.source_kind,
            source_path=candidate.source_relative_path,
            warehouse_path=str(
                Path(published.current_path).relative_to(
                    self.project_root
                )
            ).replace("\\", "/"),
            snapshot_path=(
                str(
                    Path(published.snapshot_path).relative_to(
                        self.project_root
                    )
                ).replace("\\", "/")
                if published.snapshot_path
                else ""
            ),
            row_count=published.row_count,
            column_count=published.column_count,
            source_modified_at_utc=datetime.fromtimestamp(
                candidate.source_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat(),
            migrated_at_utc=published.published_at_utc,
            refresh_id=published.refresh_id,
            status="success",
            warning="|".join(published.warnings),
        )

    def _write_reports(
        self,
        *,
        results: list[MigrationResult],
        warnings: list[str],
        errors: list[str],
        refresh_id: str,
        status: str,
    ) -> dict:
        root = self.warehouse.config.manifests_root
        root.mkdir(parents=True, exist_ok=True)

        report_path = root / "migration_report.csv"
        fieldnames = list(
            MigrationResult.__dataclass_fields__.keys()
        )
        with report_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
            )
            writer.writeheader()
            writer.writerows(
                result.to_record() for result in results
            )

        status_path = root / "migration_status.json"
        payload = {
            "status": status,
            "refresh_id": refresh_id,
            "legacy_outputs_preserved": True,
            "datasets_discovered": len(results),
            "datasets_migrated": len(results),
            "datasets_failed": len(errors),
            "warning_count": len(warnings),
            "error_count": len(errors),
            "warnings": warnings,
            "errors": errors,
            "warehouse_root": str(
                self.warehouse.config.warehouse_root
            ),
            "completed_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
        }
        status_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

        return {
            **payload,
            "migration_report": str(report_path),
            "migration_status": str(status_path),
        }


def migrate_legacy_dashboard_outputs(
    *,
    project_root: Path | None = None,
    create_snapshots: bool = True,
    include_analytics_current: bool = True,
    continue_on_error: bool = False,
) -> dict:
    return WarehouseMigration(
        project_root=project_root
    ).migrate(
        create_snapshots=create_snapshots,
        include_analytics_current=include_analytics_current,
        continue_on_error=continue_on_error,
    )
