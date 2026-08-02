from __future__ import annotations

import json
from pathlib import Path

from scripts.run_collector_v1_governance_locked_preflight import (
    BUNDLE_SHA,
    OPERATING_DATE,
    PRODUCT_COUNT,
    SNAPSHOT_ID,
    TIMEZONE,
    candidate_manifests,
    validate_manifest,
)


def write_manifest(path: Path, *, product_count: int = PRODUCT_COUNT, bundle_sha: str = BUNDLE_SHA) -> None:
    payload = {
        "snapshot_id": SNAPSHOT_ID,
        "operating_date": OPERATING_DATE,
        "timezone": TIMEZONE,
        "source_bundle_sha256": bundle_sha,
        "certified_product_count": product_count,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_exact_snapshot_manifest_is_resolved(tmp_path: Path) -> None:
    manifest = tmp_path / "august_1" / "snapshot_manifest.json"
    write_manifest(manifest)
    matches = candidate_manifests(tmp_path)
    assert matches == [manifest.resolve()]
    valid, reasons, _ = validate_manifest(matches[0])
    assert valid is True
    assert reasons == []


def test_missing_or_incorrect_snapshot_identity_fails_closed(tmp_path: Path) -> None:
    wrong = tmp_path / "snapshot_manifest.json"
    write_manifest(wrong, product_count=49)
    matches = candidate_manifests(tmp_path)
    assert matches == [wrong.resolve()]
    valid, reasons, _ = validate_manifest(matches[0])
    assert valid is False
    assert "CERTIFIED_PRODUCT_COUNT_MISMATCH" in reasons


def test_unrelated_json_is_not_accepted_as_snapshot_manifest(tmp_path: Path) -> None:
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text(json.dumps({"snapshot_id": SNAPSHOT_ID}), encoding="utf-8")
    assert candidate_manifests(tmp_path) == []


def test_multiple_exact_manifests_are_detectable(tmp_path: Path) -> None:
    write_manifest(tmp_path / "a" / "manifest.json")
    write_manifest(tmp_path / "b" / "manifest.json")
    assert len(candidate_manifests(tmp_path)) == 2
