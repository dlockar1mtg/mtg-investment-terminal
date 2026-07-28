from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PublishArtifact:
    source: Path
    filename: str
    required_columns: tuple[str, ...] = ()
    expected_rows: int | None = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_shape(path: Path) -> tuple[int, list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = sum(1 for _ in reader)
        return rows, list(reader.fieldnames or [])


def validate_artifact(artifact: PublishArtifact) -> dict:
    if not artifact.source.is_file():
        raise FileNotFoundError(str(artifact.source))

    result = {
        "filename": artifact.filename,
        "source": str(artifact.source),
        "size_bytes": artifact.source.stat().st_size,
        "sha256": sha256(artifact.source),
    }

    if artifact.source.suffix.casefold() == ".csv":
        row_count, columns = csv_shape(artifact.source)
        missing = [
            column for column in artifact.required_columns
            if column not in columns
        ]
        if missing:
            raise ValueError(
                f"{artifact.filename} missing required columns: {missing}"
            )
        if (
            artifact.expected_rows is not None
            and row_count != artifact.expected_rows
        ):
            raise ValueError(
                f"{artifact.filename}: expected {artifact.expected_rows} "
                f"rows, found {row_count}"
            )
        result["row_count"] = row_count
        result["columns"] = columns

    return result


def publish_package(
    destination_root: Path,
    package_id: str,
    artifacts: Iterable[PublishArtifact],
    metadata: dict,
) -> dict:
    destination_root.mkdir(parents=True, exist_ok=True)
    package_root = destination_root / "packages" / package_id
    latest_root = destination_root / "latest"

    if package_root.exists():
        raise FileExistsError(str(package_root))

    artifact_list = list(artifacts)
    validations = [validate_artifact(item) for item in artifact_list]

    with tempfile.TemporaryDirectory(
        prefix="mtg-delivery-", dir=destination_root
    ) as temp_name:
        stage = Path(temp_name) / package_id
        stage.mkdir(parents=True)

        for artifact in artifact_list:
            shutil.copy2(artifact.source, stage / artifact.filename)

        manifest = {
            "status": "PASS",
            "package_id": package_id,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            **metadata,
            "artifacts": validations,
        }
        (stage / "delivery_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        package_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage), str(package_root))

    latest_temp = destination_root / ".latest-next"
    if latest_temp.exists():
        shutil.rmtree(latest_temp)
    shutil.copytree(package_root, latest_temp)
    if latest_root.exists():
        shutil.rmtree(latest_root)
    latest_temp.rename(latest_root)

    pointer = {
        "package_id": package_id,
        "package_path": str(package_root),
        "latest_path": str(latest_root),
    }
    (destination_root / "latest_package.json").write_text(
        json.dumps(pointer, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
