from __future__ import annotations

import csv
import importlib.util
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/certify_collector_v1_canonical_identity_lineage_v2.py"
HISTORY = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
COMPARABLE = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_comparable_pool_certification.csv"


def load_module():
    spec = importlib.util.spec_from_file_location("collector_identity_v2", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def headers(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle).fieldnames or [])


def test_v2_certifier_exists_and_compiles() -> None:
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_historical_authority_uses_governed_canonical_product_name() -> None:
    fields = headers(HISTORY)
    assert "canonical_product_id" in fields
    assert "canonical_product_name" in fields
    assert "product_name" not in fields


def test_v2_resolver_accepts_exact_historical_schema() -> None:
    module = load_module()
    sample = [{field: "" for field in headers(HISTORY)}]
    canonical_id, tcgplayer_id, product_name = module.governed_identity_fields(sample)
    assert canonical_id == "canonical_product_id"
    assert tcgplayer_id == "tcgplayer_product_id"
    assert product_name == "canonical_product_name"


def test_comparable_pool_has_explicit_target_member_identity_schema() -> None:
    fields = headers(COMPARABLE)
    required = {
        "target_canonical_product_id",
        "target_product_name",
        "comparable_canonical_product_id",
        "comparable_product_name",
    }
    assert required.issubset(fields)


def test_v2_does_not_relax_identity_to_name_only_or_fuzzy_matching() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "canonical_product_name" in text
    assert "fuzzy" not in text.lower()
    assert "difflib" not in text.lower()
    assert "rapidfuzz" not in text.lower()
