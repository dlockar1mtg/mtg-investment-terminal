from __future__ import annotations

from pathlib import Path

import py7zr
import pytest

from terminal2.sources.archive_utils import (
    UnsafeArchiveError,
    extract_7z_archive,
    validate_archive_members,
)


def test_validate_archive_members_accepts_relative_paths():
    validate_archive_members(
        ["2024-02-08/1/2/prices", "metadata.json"]
    )


@pytest.mark.parametrize(
    "member_name",
    [
        "../outside.txt",
        "folder/../../outside.txt",
        "/absolute/path.txt",
        "C:/windows/path.txt",
    ],
)
def test_validate_archive_members_rejects_unsafe_paths(member_name):
    with pytest.raises(UnsafeArchiveError):
        validate_archive_members([member_name])


def test_extract_7z_archive_round_trip(tmp_path: Path):
    source = tmp_path / "source"
    nested = source / "2024-02-08" / "1" / "2"
    nested.mkdir(parents=True)
    (nested / "prices").write_text(
        "productId,marketPrice\n123,45.67\n",
        encoding="utf-8",
    )

    archive = tmp_path / "prices.7z"
    with py7zr.SevenZipFile(archive, mode="w") as seven_zip:
        for path in source.rglob("*"):
            if path.is_file():
                seven_zip.write(
                    path,
                    arcname=str(
                        path.relative_to(source)
                    ),
                )

    destination = tmp_path / "extracted"
    result = extract_7z_archive(archive, destination)

    assert result == destination
    assert (
        destination / "2024-02-08" / "1" / "2" / "prices"
    ).exists()


def test_existing_destination_is_cached(tmp_path: Path):
    archive = tmp_path / "unused.7z"
    archive.write_bytes(b"placeholder")

    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "marker.txt"
    marker.write_text("keep", encoding="utf-8")

    result = extract_7z_archive(
        archive,
        destination,
        force=False,
    )

    assert result == destination
    assert marker.read_text(encoding="utf-8") == "keep"
