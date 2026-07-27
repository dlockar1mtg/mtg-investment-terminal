from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_universal_tcgcsv_source_discovery.py"
    spec = importlib.util.spec_from_file_location("build_universal_tcgcsv_source_discovery", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def test_individual_card_is_not_sealed():
    module = load_module()
    row = {"group_name": "Secret Lair Drop Series", "product_name": "Abrade (1425)"}
    assert module.secret_lair_evidence(row) is True
    assert module.sealed_evidence(row) is False

def test_sealed_drop_is_sealed():
    module = load_module()
    row = {
        "group_name": "Secret Lair Drop Series",
        "product_name": "Secret Lair Drop: Artist Series: Sam Burley - Traditional Foil Edition",
    }
    assert module.sealed_evidence(row) is True

def test_exact_match_can_be_found_from_full_secret_lair_evidence():
    module = load_module()
    registry = [{
        "investment_product_id": "SL-1",
        "canonical_product_name": "Drop: Artist Series: Sam Burley - Traditional Foil Edition",
        "finish_group": "FOIL",
        "product_group": "ARTIST",
    }]
    candidate = {
        "group_name": "Secret Lair Drop Series",
        "product_name": "Secret Lair Drop: Artist Series: Sam Burley - Traditional Foil Edition",
        "tcgplayer_product_id": "480473",
    }
    metrics = module.score(registry[0], candidate)
    assert metrics["exact_normalized_name"] is True
    assert metrics["finish_match"] is True

def test_candidate_is_never_classified_not_found():
    module = load_module()
    rows = [{
        "candidate_score": 0.50,
        "exact_normalized_name": False,
        "finish_match": True,
        "tcgplayer_product_id": "1",
    }]
    status, _ = module.classify(rows)
    assert status == "TCGCSV_ID_AMBIGUOUS"

def test_no_candidate_is_not_found():
    module = load_module()
    status, _ = module.classify([])
    assert status == "TCGCSV_ID_NOT_FOUND"
