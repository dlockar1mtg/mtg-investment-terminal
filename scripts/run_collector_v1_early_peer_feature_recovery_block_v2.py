from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"

REGISTRY_ROOTS = [
    ROOT / "data/governance/permanence/certification/collector_v1_authoritative_data_registry",
    ROOT / "data/governance/permanence/certification/collector_v1_authoritative_registry",
    ROOT / "artifacts/certification/collector_boosters/candidate_v1_0_0",
]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def walk_json(value: Any, trail: tuple[str, ...] = ()):
    if isinstance(value, dict):
        yield trail, value
        for key, child in value.items():
            yield from walk_json(child, trail + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, trail + (str(index),))


def candidate_path_from_record(record: dict[str, Any]) -> str | None:
    path_keys = (
        "path", "file_path", "source_path", "resolved_path", "authority_path",
        "artifact_path", "registered_path", "relative_path",
    )
    for key in path_keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def record_text(record: dict[str, Any]) -> str:
    keys = (
        "authority", "authority_name", "name", "role", "dataset", "dataset_name",
        "description", "source_role", "logical_name", "artifact_name",
    )
    values = [str(record.get(key, "")) for key in keys]
    return " ".join(values).lower()


def resolve_path(raw: str) -> Path:
    normalized = raw.replace("\\", "/")
    path = Path(normalized)
    return path if path.is_absolute() else ROOT / path


def resolve_active_comparables_from_registry() -> tuple[Path, Path, str]:
    checked_registry_files: list[str] = []
    matches: list[tuple[Path, Path, str]] = []

    for root in REGISTRY_ROOTS:
        if not root.exists():
            continue
        for registry_file in sorted(root.glob("**/*")):
            if registry_file.suffix.lower() not in {".json", ".csv"}:
                continue
            name = registry_file.name.lower()
            if "registr" not in name and "authorit" not in name:
                continue
            checked_registry_files.append(str(registry_file.relative_to(ROOT)))

            if registry_file.suffix.lower() == ".json":
                try:
                    payload = json.loads(registry_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                for trail, record in walk_json(payload):
                    text = record_text(record)
                    path_value = candidate_path_from_record(record)
                    if not path_value:
                        continue
                    path_text = path_value.lower()
                    is_comparable = "comparable" in text or "comparable" in path_text
                    is_active = "active" in text or "active" in path_text
                    if not (is_comparable and is_active):
                        continue
                    resolved = resolve_path(path_value)
                    if resolved.exists() and resolved.suffix.lower() == ".csv":
                        matches.append((registry_file, resolved, "/".join(trail)))

            else:
                try:
                    frame = pd.read_csv(registry_file)
                except Exception:
                    continue
                for _, row in frame.iterrows():
                    record = {str(k): v for k, v in row.to_dict().items()}
                    text = record_text(record)
                    path_value = candidate_path_from_record(record)
                    if not path_value:
                        continue
                    path_text = path_value.lower()
                    is_comparable = "comparable" in text or "comparable" in path_text
                    is_active = "active" in text or "active" in path_text
                    if not (is_comparable and is_active):
                        continue
                    resolved = resolve_path(path_value)
                    if resolved.exists() and resolved.suffix.lower() == ".csv":
                        matches.append((registry_file, resolved, "csv_row"))

    unique: dict[str, tuple[Path, Path, str]] = {}
    for item in matches:
        unique[str(item[1].resolve())] = item
    matches = list(unique.values())

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one registered active comparable authority. "
            f"matches={[str(item[1]) for item in matches]}; "
            f"checked_registry_files={checked_registry_files}"
        )

    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    registry_file, comparable_path, registry_location = resolve_active_comparables_from_registry()
    print(json.dumps({
        "early_peer_feature_recovery_registry_preflight": {
            "registry_file": str(registry_file.relative_to(ROOT)),
            "registry_record_location": registry_location,
            "resolved_active_comparable_path": str(comparable_path.relative_to(ROOT)),
            "resolved_path_exists": comparable_path.exists(),
            "recursive_repository_discovery_used": False,
            "certified_source_files_mutated": False,
        }
    }, indent=2))

    builder = load_module(
        SCRIPT_DIR / "build_collector_v1_early_peer_feature_recovery.py",
        "collector_early_peer_feature_recovery_builder_v2",
    )
    original_first_existing = builder.first_existing

    def registry_aware_first_existing(paths: list[Path]) -> Path:
        names = {path.name for path in paths}
        if names & {"collector_v1_active_comparables.csv", "collector_v1_comparables.csv"}:
            return comparable_path
        return original_first_existing(paths)

    builder.first_existing = registry_aware_first_existing
    sys.argv = [str(SCRIPT_DIR / "build_collector_v1_early_peer_feature_recovery.py")]
    if args.strict:
        sys.argv.append("--strict")
    build_code = int(builder.main())
    if build_code != 0:
        print("Early peer feature recovery V2 build failed; certification was not run.")
        return build_code

    certifier = load_module(
        SCRIPT_DIR / "certify_collector_v1_early_peer_feature_recovery.py",
        "collector_early_peer_feature_recovery_certifier_v2",
    )
    sys.argv = [str(SCRIPT_DIR / "certify_collector_v1_early_peer_feature_recovery.py")]
    if args.strict:
        sys.argv.append("--strict")
    cert_code = int(certifier.main())
    if cert_code != 0:
        print("Early peer feature recovery V2 certification failed.")
        return cert_code

    print("PASS_COLLECTOR_V1_EARLY_PEER_FEATURE_RECOVERY_BLOCK_V2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
