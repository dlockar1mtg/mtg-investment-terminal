from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts/run_precollector_horizon_tournaments_from_certified_bundle.py"
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_horizon_tournament_execution_from_certified_bundle_contract_v1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_bound_history(contract: dict) -> tuple[list[dict[str, str]], dict[str, object]]:
    binding = contract["canonical_history_binding"]
    package_path = Path(tempfile.gettempdir()) / binding["package_name"]
    if not package_path.is_file():
        raise RuntimeError("BOUND_CANONICAL_HISTORY_PACKAGE_MISSING")
    package_hash = sha256_file(package_path)
    if package_hash != binding["package_sha256"]:
        raise RuntimeError("BOUND_CANONICAL_HISTORY_PACKAGE_HASH_DRIFT")
    with zipfile.ZipFile(package_path) as archive:
        try:
            payload = archive.read(binding["member_name"])
        except KeyError as exc:
            raise RuntimeError("BOUND_CANONICAL_HISTORY_MEMBER_MISSING") from exc
    member_hash = hashlib.sha256(payload).hexdigest()
    if member_hash != binding["member_sha256"]:
        raise RuntimeError("BOUND_CANONICAL_HISTORY_MEMBER_HASH_DRIFT")
    text = payload.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    missing = [column for column in binding["required_columns"] if column not in headers]
    if missing:
        raise RuntimeError("BOUND_CANONICAL_HISTORY_SCHEMA_DRIFT:" + ",".join(missing))
    rows = list(reader)
    expected_rows = int(contract["expected_canonical_historical_rows"])
    if len(rows) != expected_rows:
        raise RuntimeError(
            f"BOUND_CANONICAL_HISTORY_ROW_COUNT_DRIFT:expected={expected_rows}:actual={len(rows)}"
        )
    normalized = []
    for row in rows:
        enriched = dict(row)
        enriched["observation_date"] = row["observation_timestamp"]
        enriched["historical_price"] = row["canonical_historical_price"]
        normalized.append(enriched)
    lineage = {
        "artifact_role": "CANONICAL_HISTORICAL_PRICE",
        "package_name": binding["package_name"],
        "member_name": binding["member_name"],
        "member_sha256": member_hash,
        "row_count": len(rows),
    }
    return normalized, lineage


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("precollector_round_one_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError("ROUND_ONE_BASE_MODULE_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    original_load = module.load_certified_inputs

    def load_certified_inputs_bound(active_contract: dict):
        artifacts, lineage, diagnostics = original_load(active_contract)
        rows, history_lineage = read_bound_history(contract)
        artifacts["CANONICAL_HISTORICAL_PRICE"] = rows
        lineage = [
            row for row in lineage
            if row.get("artifact_role") != "CANONICAL_HISTORICAL_PRICE"
        ]
        lineage.append(history_lineage)
        return artifacts, lineage, diagnostics

    module.load_certified_inputs = load_certified_inputs_bound
    result = int(module.main())
    if result == 0:
        print("PASS_PRECOLLECTOR_EXACT_CANONICAL_HISTORY_BINDING_V1_1")
        print(f"CANONICAL_HISTORY_ROWS={contract['expected_canonical_historical_rows']}")
        print("CANONICAL_HISTORY_MEMBER_HASH_VERIFIED=TRUE")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
