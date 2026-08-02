from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "scripts/certify_collector_v1_canonical_identity_lineage.py"


def load_base_module():
    spec = importlib.util.spec_from_file_location(
        "collector_canonical_identity_lineage_base",
        BASE_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load base certifier from {BASE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = load_base_module()


def governed_identity_fields(
    rows: list[dict[str, str]],
) -> tuple[str, str | None, str]:
    """Resolve the exact certified single-product identity schema.

    Historical observations use ``canonical_product_name`` while the other
    single-product authorities use ``product_name``. Comparable-pool target and
    member identities remain governed by the dedicated target/member logic in
    the base certifier and do not pass through this resolver.
    """
    canonical_id = base.find_field(
        rows,
        ["canonical_product_id", "product_id", "asset_id"],
    )
    tcgplayer_id = base.find_field(
        rows,
        ["tcgplayer_product_id", "resolved_tcgplayer_product_id"],
        required=False,
    )
    product_name = base.find_field(
        rows,
        ["product_name", "canonical_product_name", "name", "asset_name"],
    )
    return canonical_id, tcgplayer_id, product_name


def main() -> int:
    base.identity_fields = governed_identity_fields
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
