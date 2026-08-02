from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EARLY_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation"
BUILDER_PATH = ROOT / "scripts/run_collector_v1_targeted_blocked_cell_remediation.py"
CERTIFIER_PATH = ROOT / "scripts/certify_collector_v1_targeted_blocked_cell_remediation.py"

CUTOFF_NAMES = {
    "collector_v1_release_age_cutoffs.csv",
    "collector_v1_release_age_cutoff_dataset.csv",
}
PEER_NAME = "collector_v1_peer_maturity_curves.csv"
PEER_AUTHORITY_FIELDS = {
    "peer_return_90d_median",
    "peer_return_180d_median",
    "peer_return_365d_median",
    "peer_return_365d_mean",
    "peer_winner_25_rate",
    "peer_winner_50_rate",
    "peer_loss_rate",
    "peer_return_365d_dispersion",
    "peer_count",
    "selected_peer_count",
    "unique_peer_count",
}


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(f"No governed candidate path exists: {[str(p) for p in paths]}")


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("collector_targeted_remediation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load governed builder: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    strict = "--strict" in sys.argv[1:]
    cutoff_path = first_existing([
        EARLY_DIR / "collector_v1_release_age_cutoffs.csv",
        EARLY_DIR / "collector_v1_release_age_cutoff_dataset.csv",
    ])
    peer_path = EARLY_DIR / PEER_NAME
    if not peer_path.exists():
        raise FileNotFoundError(f"Governed peer maturity authority missing: {peer_path}")

    raw_cutoffs = pd.read_csv(cutoff_path)
    raw_peers = pd.read_csv(peer_path)
    duplicate_peer_fields = sorted(
        set(raw_cutoffs.columns)
        & set(raw_peers.columns)
        & PEER_AUTHORITY_FIELDS
    )
    required_peer_candidates = [
        "peer_return_365d_median",
        "return_365d_median",
        "median_return_365d",
    ]
    resolved_peer_median = next(
        (name for name in required_peer_candidates if name in raw_peers.columns),
        None,
    )
    preflight = {
        "cutoff_path": str(cutoff_path.relative_to(ROOT)),
        "peer_authority_path": str(peer_path.relative_to(ROOT)),
        "duplicate_peer_fields_removed_from_in_memory_cutoff_copy": duplicate_peer_fields,
        "resolved_peer_median_column": resolved_peer_median,
        "peer_authority_precedence": True,
        "certified_source_files_mutated": False,
    }
    print(json.dumps({"targeted_remediation_schema_preflight": preflight}, indent=2))
    if resolved_peer_median is None:
        raise ValueError(
            "Peer maturity authority lacks a governed 365-day median return column. "
            f"available={list(raw_peers.columns)}"
        )

    module = load_module(BUILDER_PATH)
    original_read_csv = module.pd.read_csv

    def governed_read_csv(path, *args, **kwargs):
        frame = original_read_csv(path, *args, **kwargs)
        candidate = Path(path)
        if candidate.name in CUTOFF_NAMES:
            removable = [column for column in duplicate_peer_fields if column in frame.columns]
            if removable:
                frame = frame.drop(columns=removable)
        return frame

    module.pd.read_csv = governed_read_csv
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(BUILDER_PATH)] + (["--strict"] if strict else [])
        build_code = int(module.main())
    finally:
        sys.argv = original_argv
        module.pd.read_csv = original_read_csv

    if build_code != 0:
        print("Targeted blocked-cell remediation build failed; certification was not run.")
        return build_code

    cert_command = [sys.executable, str(CERTIFIER_PATH)]
    if strict:
        cert_command.append("--strict")
    cert_result = subprocess.run(cert_command, cwd=ROOT, check=False)
    if cert_result.returncode != 0:
        print("Targeted blocked-cell remediation certification failed.")
        return int(cert_result.returncode)

    print("PASS_COLLECTOR_V1_TARGETED_BLOCKED_CELL_REMEDIATION_BLOCK_V2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
