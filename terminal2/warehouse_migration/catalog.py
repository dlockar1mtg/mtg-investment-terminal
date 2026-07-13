from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from terminal2.warehouse_core.paths import normalize_dataset_name


CATEGORY_DIRECTORIES = {
    "executive": "executive",
    "products": "products",
    "market": "market",
    "lifecycle": "lifecycle",
    "portfolio": "portfolio",
    "seasonality": "seasonality",
    "research": "research",
    "alerts": "alerts",
    "metadata": "metadata",
    "rankings": "rankings",
    "intelligence": "intelligence",
    "admin": "admin",
}

EXCLUDED_FILENAMES = {
    "dataset_manifest.csv",
    "data_dictionary.csv",
}


@dataclass(frozen=True)
class MigrationCandidate:
    dataset_name: str
    category: str
    source_path: Path
    source_kind: str
    source_relative_path: str
    snapshot: bool = True


def _dashboard_category(relative_path: Path) -> str:
    if len(relative_path.parts) >= 2:
        directory = relative_path.parts[0].lower()
        if directory in CATEGORY_DIRECTORIES:
            return CATEGORY_DIRECTORIES[directory]
    return "admin"


def discover_legacy_datasets(
    project_root: Path,
    *,
    include_analytics_current: bool = True,
) -> tuple[list[MigrationCandidate], list[str]]:
    project_root = Path(project_root).resolve()
    dashboard_root = project_root / "data" / "dashboard"
    analytics_root = project_root / "data" / "analytics" / "current"

    candidates: list[MigrationCandidate] = []
    warnings: list[str] = []

    if dashboard_root.exists():
        for path in sorted(dashboard_root.rglob("*.csv")):
            if path.name.lower() in EXCLUDED_FILENAMES:
                continue
            relative = path.relative_to(dashboard_root)
            candidates.append(
                MigrationCandidate(
                    dataset_name=normalize_dataset_name(relative.stem),
                    category=_dashboard_category(relative),
                    source_path=path,
                    source_kind="dashboard",
                    source_relative_path=str(
                        path.relative_to(project_root)
                    ).replace("\\", "/"),
                    snapshot=True,
                )
            )
    else:
        warnings.append(
            f"Legacy dashboard directory does not exist: {dashboard_root}"
        )

    if include_analytics_current and analytics_root.exists():
        for path in sorted(analytics_root.rglob("*.csv")):
            if path.name.lower() in EXCLUDED_FILENAMES:
                continue
            candidates.append(
                MigrationCandidate(
                    dataset_name=normalize_dataset_name(
                        f"current_{path.stem}"
                    ),
                    category="research",
                    source_path=path,
                    source_kind="analytics_current",
                    source_relative_path=str(
                        path.relative_to(project_root)
                    ).replace("\\", "/"),
                    snapshot=False,
                )
            )

    selected: dict[str, MigrationCandidate] = {}
    for candidate in candidates:
        if candidate.dataset_name in selected:
            warnings.append(
                f"Duplicate dataset source ignored: "
                f"{candidate.source_relative_path}"
            )
            continue
        selected[candidate.dataset_name] = candidate

    return (
        sorted(
            selected.values(),
            key=lambda item: (item.category, item.dataset_name),
        ),
        warnings,
    )
