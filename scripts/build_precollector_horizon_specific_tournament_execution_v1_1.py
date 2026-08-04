from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts/build_precollector_horizon_specific_tournament_execution.py"
ARCHITECTURE_DIR = ROOT / "artifacts/precollector/horizon_specific_tournament_architecture"
CANONICAL_ARCHITECTURE = ARCHITECTURE_DIR / "precollector_horizon_specific_tournament_architecture.csv"
LEGACY_EXPECTED_ARCHITECTURE = ARCHITECTURE_DIR / "precollector_horizon_tournament_architecture.csv"


def main() -> int:
    spec = importlib.util.spec_from_file_location("precollector_horizon_execution_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_HORIZON_EXECUTION_MODULE_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    original_run = module.run

    def corrected_run(command: list[str]) -> None:
        original_run(command)
        if CANONICAL_ARCHITECTURE.is_file():
            shutil.copy2(CANONICAL_ARCHITECTURE, LEGACY_EXPECTED_ARCHITECTURE)
        else:
            raise RuntimeError("CANONICAL_HORIZON_ARCHITECTURE_OUTPUT_MISSING")

    module.run = corrected_run
    result = int(module.main())
    if result == 0:
        print("PASS_PRECOLLECTOR_HORIZON_EXECUTION_ARCHITECTURE_INTERFACE_CORRECTION_V1_1")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
