from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "apply_mtg_live_uip_overlay.py"
    spec = importlib.util.spec_from_file_location("phase_11e_overlay_join", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_composite_tcgcsv_id_exposes_trailing_tcgplayer_id():
    module = load_module()
    values = module.identifiers({"source_product_id": "TCGCSV-3070-271509"})
    assert "TCGCSV-3070-271509" in values
    assert "271509" in values


def test_forecast_resolves_tcgplayer_id_through_asset_master():
    module = load_module()
    asset_id = "MTG:COLLECTOR_BOOSTER_BOX:TCGCSV-3070-271509"
    aliases = module.build_asset_aliases([{
        "asset_id": asset_id,
        "source_product_id": "TCGCSV-3070-271509",
        "tcgplayer_product_id": "271509",
    }])
    values = module.row_identifiers({"asset_id": asset_id}, aliases)
    assert "271509" in values
    assert "TCGCSV-3070-271509" in values
