from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    runner = load_module(ROOT / "scripts/run_collector_v1_final_purchase_adequacy_tournament.py", "final_purchase_runner")
    run_code = int(runner.main())
    if run_code != 0:
        print("Final purchase adequacy tournament did not pass all gates; certification was not run.")
        return run_code

    certifier = load_module(ROOT / "scripts/certify_collector_v1_final_purchase_adequacy_tournament.py", "final_purchase_certifier")
    cert_code = int(certifier.main())
    if cert_code == 0:
        print("PASS_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_TOURNAMENT_BLOCK")
    return cert_code


if __name__ == "__main__":
    raise SystemExit(main())
