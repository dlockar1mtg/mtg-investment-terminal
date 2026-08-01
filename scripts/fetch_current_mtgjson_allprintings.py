"""Fetch, verify, and immutably vault the current official MTGJSON AllPrintings dataset."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_URL = "https://mtgjson.com/api/v5/AllPrintings.json.bz2"
HASH_URL = DATA_URL + ".sha256"
RAW_ROOT = ROOT / "data/raw/mtgjson/current"
VAULT_ROOT = ROOT / "data_vault/raw/mtg/collector_booster/mtgjson_allprintings"
CERT_ROOT = ROOT / "data/governance/permanence/certification/collector_mtgjson_current_source"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    retrieval_id = now.strftime("mtgjson-allprintings-%Y%m%dT%H%M%SZ")
    raw_dir = RAW_ROOT / retrieval_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    CERT_ROOT.mkdir(parents=True, exist_ok=True)

    compressed = raw_dir / "AllPrintings.json.bz2"
    sidecar = raw_dir / "AllPrintings.json.bz2.sha256"

    with requests.get(HASH_URL, timeout=args.timeout) as response:
        response.raise_for_status()
        sidecar.write_bytes(response.content)
    expected = sidecar.read_text(encoding="utf-8-sig").strip().split()[0].lower()

    with requests.get(DATA_URL, timeout=args.timeout, stream=True) as response:
        response.raise_for_status()
        with compressed.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)

    actual = sha256_file(compressed)
    verified = bool(expected and actual == expected)
    vault_path = VAULT_ROOT / f"sha256-{actual[:16]}" / "AllPrintings.json.bz2"
    if verified:
        vault_path.parent.mkdir(parents=True, exist_ok=True)
        if not vault_path.exists():
            shutil.copy2(compressed, vault_path)

    metadata = {
        "source_name": "MTGJSON_ALLPRINTINGS",
        "source_url": DATA_URL,
        "sha256_url": HASH_URL,
        "retrieval_id": retrieval_id,
        "retrieved_at": now.isoformat(),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "sha256_verified": verified,
        "compressed_bytes": compressed.stat().st_size,
        "raw_path": str(compressed.relative_to(ROOT)).replace("\\", "/"),
        "vault_path": str(vault_path.relative_to(ROOT)).replace("\\", "/") if verified else "",
        "immutable_vault_written": verified and vault_path.is_file(),
        "status": "PASS_CURRENT_MTGJSON_SOURCE_VERIFIED" if verified else "FAIL_HASH_MISMATCH",
    }
    (raw_dir / "source_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (CERT_ROOT / "collector_mtgjson_current_source_summary.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    (CERT_ROOT / "current_source_pointer.json").write_text(
        json.dumps({"retrieval_id": retrieval_id, "vault_path": metadata["vault_path"], "sha256": actual}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2))
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
