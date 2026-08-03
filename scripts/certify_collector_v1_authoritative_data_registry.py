from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/mtg/governance/collector_v1_authoritative_data_registry.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_data_registry"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    results = {}
    failures = []

    for name, spec in registry["authorities"].items():
        path = ROOT / spec["path"]
        exists = path.is_file()
        record = {
            "path": spec["path"],
            "role": spec["role"],
            "exists": exists,
            "sha256": sha256(path) if exists else None,
            "size_bytes": path.stat().st_size if exists else None,
        }
        results[name] = record
        if not exists:
            failures.append({"authority": name, "path": spec["path"], "reason": "REGISTERED_INPUT_MISSING"})

    certified = len(failures) == 0
    summary = {
        "block_name": "Collector V1 Authoritative Data Registry Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_path": str(REGISTRY.relative_to(ROOT)).replace("\\", "/"),
        "registered_authority_count": len(results),
        "registered_authorities": results,
        "failures": failures,
        "authoritative_dependency_chain_certified": certified,
        "forecast_feature_builders_must_use_registry": True,
        "recursive_discovery_permitted_for_authoritative_selection": False,
        "status": "PASS_COLLECTOR_V1_AUTHORITATIVE_DATA_REGISTRY_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_AUTHORITATIVE_DATA_REGISTRY",
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_v1_authoritative_data_registry_certification.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and not certified else 0


if __name__ == "__main__":
    raise SystemExit(main())
