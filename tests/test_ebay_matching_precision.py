from __future__ import annotations

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources import ebay_universe
from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision import run_coverage, strict_match_listing


def product(name: str = "Alpha Edition - Booster Box") -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id="MTG-TEST",
        canonical_product_name=name,
        canonical_set_name=name.replace(" - Booster Box", ""),
        product_class="PRE_COLLECTOR_BOOSTER_BOX",
        tcgplayer_product_id="1",
        release_date="1993-08-05",
        ebay_query="query",
    )


def listing(title: str) -> dict[str, object]:
    return {
        "itemId": "1",
        "title": title,
        "price": {"value": "100.00", "currency": "USD"},
        "condition": "New/Factory Sealed",
    }


def test_unrelated_alpha_tcg_is_rejected():
    result = strict_match_listing(
        product(),
        listing("Sorcery Contested Realm TCG Alpha Booster Box Factory Sealed"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "unrelated_game" in result.exclusion_reasons
    assert "missing_mtg_identity" in result.exclusion_reasons


def test_real_magic_alpha_box_can_be_accepted():
    result = strict_match_listing(
        product(),
        listing("Magic The Gathering Alpha Edition Booster Box Factory Sealed WOTC"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "ACCEPTED"


def test_loose_packs_are_rejected_not_reviewed():
    result = strict_match_listing(
        product("10th Edition - Booster Box"),
        listing("MTG 10th Edition Factory Sealed Booster 5 Packs"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "missing_booster_box_form" in result.exclusion_reasons
    assert "loose_packs" in result.exclusion_reasons


def test_wrong_alara_set_is_rejected():
    result = strict_match_listing(
        product("Alara Reborn - Booster Box"),
        listing("MTG Shards of Alara Factory Sealed Booster Box"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "insufficient_product_identity" in result.exclusion_reasons


def test_plural_booster_boxes_count_as_box_form():
    result = strict_match_listing(
        product("Amonkhet - Booster Box"),
        listing("MTG Magic the Gathering Amonkhet Booster Boxes Factory Sealed"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert "missing_booster_box_form" not in result.exclusion_reasons


def test_precision_runner_uses_strict_matcher_without_recursion(monkeypatch, tmp_path):
    sample_product = product("Amonkhet - Booster Box")

    monkeypatch.setattr(
        ebay_universe,
        "ORIGINAL_BUILD_UNIVERSE",
        lambda: [sample_product],
    )
    monkeypatch.setattr(
        ebay_universe,
        "load_operational_collector_products",
        lambda db_file=ebay_universe.DB_FILE: [],
    )
    monkeypatch.setattr(base, "OUTPUT_ROOT", tmp_path)

    class FakeClient:
        def search_product(self, product, limit=20):
            return [listing("MTG Magic the Gathering Amonkhet Booster Box Factory Sealed")], 1

    monkeypatch.setattr(base, "EbayBrowseClient", FakeClient)

    summary = run_coverage(limit_per_product=20, max_products=1)

    assert summary["products"] == 1
    assert summary["listing_rows"] == 1
    assert summary["accepted_rows"] == 1
    assert summary["coverage_states"] == {"LIMITED_MATCH_COVERAGE": 1}
