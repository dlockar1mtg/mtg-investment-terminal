from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts/run_collector_v1_targeted_blocked_cell_remediation.py"
CERTIFIER_PATH = ROOT / "scripts/certify_collector_v1_targeted_blocked_cell_remediation.py"
PEER_PATH = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation/collector_v1_peer_maturity_curves.csv"


def load_builder_module():
    spec = importlib.util.spec_from_file_location("collector_targeted_remediation_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load builder module: {BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_certifier(strict: bool) -> int:
    command = [sys.executable, str(CERTIFIER_PATH)]
    if strict:
        command.append("--strict")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if not PEER_PATH.exists():
        raise FileNotFoundError(f"Peer maturity authority not found: {PEER_PATH}")

    peer_columns = list(pd.read_csv(PEER_PATH, nrows=0).columns)
    target_present = "target_product_id" in peer_columns
    generic_present = "tcgplayer_product_id" in peer_columns

    preflight = {
        "targeted_remediation_identity_preflight": {
            "peer_authority_path": str(PEER_PATH.relative_to(ROOT)),
            "target_product_id_present": target_present,
            "tcgplayer_product_id_present": generic_present,
            "selected_target_identity_column": "target_product_id" if target_present else "tcgplayer_product_id",
            "identity_role_precedence": "TARGET_PRODUCT_ID_FIRST",
            "certified_source_files_mutated": False,
        }
    }
    print(json.dumps(preflight, indent=2))

    if not target_present and not generic_present:
        print("Peer authority has no usable target identity column.", file=sys.stderr)
        return 1

    module = load_builder_module()
    original_first_col = module.first_col

    def role_aware_first_col(df, names, required=True):
        # The peer-maturity authority may carry both target and peer/product IDs.
        # For target-side joins, target_product_id is authoritative and must win.
        if "target_product_id" in df.columns and any(
            name in names for name in ["tcgplayer_product_id", "target_product_id", "product_id"]
        ):
            return "target_product_id"
        return original_first_col(df, names, required=required)

    module.first_col = role_aware_first_col

    original_argv = sys.argv[:]
    try:
        sys.argv = [str(BUILDER_PATH)] + (["--strict"] if args.strict else [])
        build_code = int(module.main())
    finally:
        sys.argv = original_argv

    if build_code != 0:
        print("Targeted blocked-cell remediation build failed; certification was not run.", file=sys.stderr)
        return build_code

    cert_code = run_certifier(args.strict)
    if cert_code != 0:
        print("Targeted blocked-cell remediation certification failed.", file=sys.stderr)
        return cert_code

    print("PASS_COLLECTOR_V1_TARGETED_BLOCKED_CELL_REMEDIATION_BLOCK_V3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
