from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    builder = load_module("collector_v1_long_horizon_builder", ROOT / "scripts/run_collector_v1_long_horizon_simulation_tournament.py")
    certifier = load_module("collector_v1_long_horizon_certifier", ROOT / "scripts/certify_collector_v1_long_horizon_simulation_tournament.py")

    import sys
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(ROOT / "scripts/run_collector_v1_long_horizon_simulation_tournament.py")] + (["--strict"] if args.strict else [])
        build_code = int(builder.main())
        if build_code != 0:
            print("Long-horizon simulation tournament did not resolve all method routes; certification was not run.")
            return build_code

        sys.argv = [str(ROOT / "scripts/certify_collector_v1_long_horizon_simulation_tournament.py")] + (["--strict"] if args.strict else [])
        cert_code = int(certifier.main())
        if cert_code != 0:
            print("Long-horizon simulation tournament certification failed.")
            return cert_code
    finally:
        sys.argv = original_argv

    print("PASS_COLLECTOR_V1_LONG_HORIZON_SIMULATION_TOURNAMENT_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
