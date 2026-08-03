from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_collector_v1_comparable_cluster_envelope_remediation as builder
import certify_collector_v1_comparable_cluster_envelope_remediation as certifier


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    original = sys.argv[:]
    try:
        sys.argv = ["run_collector_v1_comparable_cluster_envelope_remediation.py"] + (["--strict"] if args.strict else [])
        build_code = int(builder.main())
        if build_code != 0:
            print("Comparable cluster-envelope remediation did not resolve the final route; certification was not run.")
            return build_code
        sys.argv = ["certify_collector_v1_comparable_cluster_envelope_remediation.py"] + (["--strict"] if args.strict else [])
        certify_code = int(certifier.main())
        if certify_code != 0:
            return certify_code
    finally:
        sys.argv = original

    print("PASS_COLLECTOR_V1_COMPARABLE_CLUSTER_ENVELOPE_REMEDIATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
