from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "scripts/build_precollector_83_product_taxonomy_method_routing.py"
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_79_product_taxonomy_method_routing_contract_v1.json"
OUTPUT_DIR = ROOT / "artifacts/precollector/79_product_taxonomy_method_routing"


def main() -> int:
    spec = importlib.util.spec_from_file_location("precollector_79_routing_base", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_83_PRODUCT_ROUTING_MODULE_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CONTRACT_PATH = CONTRACT_PATH
    module.OUTPUT_DIR = OUTPUT_DIR
    result = int(module.main())
    if result == 0:
        print("PASS_PRECOLLECTOR_79_PRODUCT_TAXONOMY_METHOD_ROUTING_RECONCILIATION")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
