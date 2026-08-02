from __future__ import annotations

import json
from pathlib import Path

from scripts.run_collector_v1_governance_locked_preflight import (
    BUNDLE_SHA,
    OPERATING_DATE,
    PRODUCT_COUNT,
    SNAPSHOT_ID,
    TIMEZONE,
    adjudicate_manifest,
    candidate_manifests,
    validate_manifest,
)


def write_manifest(
    path: Path,
    *,
    product_count: int = PRODUCT_COUNT,
    bundle_sha: str = BUNDLE_SHA,
) -> None:
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
    manifest = tmp_path / "snapshots" / "2026-08-01" / "snapshot_manifest.json"
    write_manifest(manifest)
    matches = candidate_manifests(tmp_path)
    assert matches == [manifest.resolve()]
    adjudication = adjudicate_manifest(matches[0])
    assert adjudication["candidate_role"] == "AUTHORITATIVE_SNAPSHOT_MANIFEST"
    valid, reasons, _ = validate_manifest(matches[0])
    assert valid is True
    assert reasons == []


def test_missing_or_incorrect_snapshot_identity_fails_closed(tmp_path: Path) -> None:
    wrong = tmp_path / "snapshots" / "2026-08-01" / "snapshot_manifest.json"
    write_manifest(wrong, product_count=49)
    matches = candidate_manifests(tmp_path)
    assert matches == [wrong.resolve()]
    adjudication = adjudicate_manifest(matches[0])
    assert adjudication["candidate_role"] == "REJECTED"
    valid, reasons, _ = validate_manifest(matches[0])
    assert valid is False
    assert "CERTIFIED_PRODUCT_COUNT_MISMATCH" in reasons


def test_unrelated_json_is_not_accepted_as_snapshot_manifest(tmp_path: Path) -> None:
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text(json.dumps({"snapshot_id": SNAPSHOT_ID}), encoding="utf-8")
    assert candidate_manifests(tmp_path) == []


def test_certification_copy_is_not_authoritative(tmp_path: Path) -> None:
    copied = (
        tmp_path
        / "data"
        / "governance"
        / "permanence"
        / "certification"
        / "2026-08-01"
        / "snapshot_manifest.json"
    )
    write_manifest(copied)
    adjudication = adjudicate_manifest(copied.resolve())
    assert adjudication["identity_match"] is True
    assert adjudication["candidate_role"] == "IDENTITY_COPY_NOT_AUTHORITATIVE"
    assert "GENERATED_OR_NONAUTHORITATIVE_COPY" in adjudication["rejection_reasons"]


def test_non_manifest_summary_is_not_authoritative(tmp_path: Path) -> None:
    copied = tmp_path / "snapshots" / "2026-08-01" / "governance_summary.json"
    write_manifest(copied)
    adjudication = adjudicate_manifest(copied.resolve())
    assert adjudication["identity_match"] is True
    assert adjudication["candidate_role"] == "IDENTITY_COPY_NOT_AUTHORITATIVE"
    assert "FILENAME_NOT_MANIFEST_AUTHORITY" in adjudication["rejection_reasons"]


def test_multiple_raw_matches_can_resolve_to_one_authoritative_manifest(tmp_path: Path) -> None:
    authoritative = tmp_path / "snapshots" / "2026-08-01" / "snapshot_manifest.json"
    copied = (
        tmp_path
        / "governance"
        / "permanence"
        / "certification"
        / "2026-08-01"
        / "snapshot_manifest.json"
    )
    write_manifest(authoritative)
    write_manifest(copied)
    matches = candidate_manifests(tmp_path)
    adjudications = [adjudicate_manifest(path) for path in matches]
    authority = [
        row
        for row in adjudications
        if row["candidate_role"] == "AUTHORITATIVE_SNAPSHOT_MANIFEST"
    ]
    assert len(matches) == 2
    assert len(authority) == 1
    assert authority[0]["candidate_path"].endswith("snapshots/2026-08-01/snapshot_manifest.json")


def test_two_true_authoritative_manifests_remain_ambiguous(tmp_path: Path) -> None:
    first = tmp_path / "snapshots" / "2026-08-01" / "snapshot_manifest.json"
    second = tmp_path / "operations" / "august_1" / "package_manifest.json"
    write_manifest(first)
    write_manifest(second)
    adjudications = [adjudicate_manifest(path) for path in candidate_manifests(tmp_path)]
    authority = [
        row
        for row in adjudications
        if row["candidate_role"] == "AUTHORITATIVE_SNAPSHOT_MANIFEST"
    ]
    assert len(authority) == 2
