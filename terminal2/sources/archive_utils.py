from __future__ import annotations

import shutil
import tempfile
from pathlib import Path, PurePosixPath

import py7zr


class UnsafeArchiveError(ValueError):
    pass


def validate_archive_members(member_names: list[str]) -> None:
    for raw_name in member_names:
        normalized = raw_name.replace("\\", "/")
        member = PurePosixPath(normalized)

        if not normalized or normalized in {".", "./"}:
            continue
        if member.is_absolute():
            raise UnsafeArchiveError(
                f"Archive member uses an absolute path: {raw_name}"
            )
        if member.parts and member.parts[0].endswith(":"):
            raise UnsafeArchiveError(
                f"Archive member uses a drive path: {raw_name}"
            )
        if ".." in member.parts:
            raise UnsafeArchiveError(
                f"Archive member escapes the destination: {raw_name}"
            )


def extract_7z_archive(
    archive_path: str | Path,
    destination: str | Path,
    *,
    force: bool = False,
) -> Path:
    archive = Path(archive_path)
    target = Path(destination)

    if not archive.is_file():
        raise FileNotFoundError(f"Archive does not exist: {archive}")
    if archive.stat().st_size <= 0:
        raise ValueError(f"Archive is empty: {archive}")
    if target.exists() and not force:
        return target

    target.parent.mkdir(parents=True, exist_ok=True)

    with py7zr.SevenZipFile(archive, mode="r") as seven_zip:
        validate_archive_members(list(seven_zip.getnames()))

    temp_root = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.extracting-",
            dir=target.parent,
        )
    )

    try:
        with py7zr.SevenZipFile(archive, mode="r") as seven_zip:
            seven_zip.extractall(path=temp_root)

        if target.exists():
            shutil.rmtree(target)

        temp_root.replace(target)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise

    return target
