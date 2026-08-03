from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    builder = load_module("collector_lower_tail_builder", SCRIPTS / "run_collector_v1_lower_tail_interval_remediation.py")
    certifier = load_module("collector_lower_tail_certifier", SCRIPTS / "certify_collector_v1_lower_tail_interval_remediation.py")

    build_code = int(builder.main())
    if build_code != 0:
        print("Lower-tail interval remediation did not resolve the final blocked cell; certification was not run.")
        return build_code if args.strict else 0

    certify_code = int(certifier.main())
    if certify_code != 0:
        print("Lower-tail interval remediation certification failed.")
        return certify_code if args.strict else 0

    print("PASS_COLLECTOR_V1_LOWER_TAIL_INTERVAL_REMEDIATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
