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


def collector_product(name: str) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id="MTG-COLLECTOR-TEST",
        canonical_product_name=name,
        canonical_set_name=name.replace(" Collector Booster Display", ""),
        product_class="COLLECTOR_BOOSTER_BOX",
        tcgplayer_product_id="2",
        release_date="2025-01-01",
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


def test_multi_box_case_is_rejected():
    result = strict_match_listing(
        collector_product("FINAL FANTASY Collector Booster Display"),
        listing("MTG Final Fantasy Collector CASE (6 sealed booster boxes)"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "multi_box_case" in result.exclusion_reasons


def test_acrylic_protective_case_does_not_trigger_multi_box_case():
    result = strict_match_listing(
        collector_product("Innistrad Remastered Collector Booster Display"),
        listing("MTG Innistrad Remastered Collector Booster Box Sealed W/ Acrylic Case"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert "multi_box_case" not in result.exclusion_reasons


def test_omega_one_pack_box_is_rejected():
    result = strict_match_listing(
        collector_product("Edge of Eternities Collector Booster Display"),
        listing("MTG Edge of Eternities Collector Omega Booster Box Sealed - 1 Pack"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "single_pack_collector_product" in result.exclusion_reasons


def test_one_fifteen_card_pack_box_is_rejected():
    result = strict_match_listing(
        collector_product("Innistrad: Midnight Hunt Collector Booster Display"),
        listing("MTG Innistrad Midnight Hunt Collector Booster Box One 15 Card Pack"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "single_pack_collector_product" in result.exclusion_reasons


def test_original_commander_legends_rejects_baldurs_gate_listing():
    result = strict_match_listing(
        collector_product("Commander Legends Collector Booster Display"),
        listing("MTG Commander Legends Battle for Baldur's Gate Collector Display Box Sealed"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_baldurs_gate_product_can_match_baldurs_gate_listing():
    result = strict_match_listing(
        collector_product(
            "Commander Legends: Battle for Baldur's Gate Collector Booster Display"
        ),
        listing("MTG Commander Legends Battle for Baldur's Gate Collector Display Box Sealed"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert "conflicting_set_identity" not in result.exclusion_reasons


def test_multi_unit_booster_box_lot_is_rejected():
    result = strict_match_listing(
        collector_product("Tarkir: Dragonstorm Collector Booster Display"),
        listing("MTG Tarkir Dragonstorm TDM LOT of 2 Collector Booster Boxes NEW Sealed Magic"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "multi_unit_lot" in result.exclusion_reasons


def test_non_acrylic_display_case_is_routed_to_review():
    result = strict_match_listing(
        collector_product("Universes Beyond: Assassin's Creed Collector Booster Display"),
        listing("MTG Universes Beyond Assassin's Creed Collector Booster Display Case ACR"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REVIEW"
    assert "ambiguous_display_case" in result.exclusion_reasons


def test_deprecated_catalog_placeholder_is_rejected():
    result = strict_match_listing(
        product("10th Edition - Booster Box"),
        listing("Booster Box [Deprecated] 10th Edition Core Set Booster Box Magic"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "deprecated_catalog_placeholder" in result.exclusion_reasons


def test_incomplete_pack_plus_box_lot_is_rejected():
    result = strict_match_listing(
        product("Chronicles - Booster Box"),
        listing("Magic Chronicles Booster Box lot of 26 packs + box"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "incomplete_pack_box_lot" in result.exclusion_reasons


def test_tournament_pack_display_is_rejected():
    result = strict_match_listing(
        product("Champions of Kamigawa - Booster Box"),
        listing("Magic Champions of Kamigawa Tournament Pack Display Box Sealed"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_mixed_product_add_on_is_rejected():
    result = strict_match_listing(
        product("Battlebond - Booster Box"),
        listing("Battlebond Booster Box Sealed + Kaldheim Collector Booster Magic"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "mixed_product_listing" in result.exclusion_reasons


def test_damaged_wrap_is_rejected():
    result = strict_match_listing(
        product("Chronicles - Booster Box"),
        listing("MTG Chronicles Booster Box Factory Sealed 45 Packs WRAP DAMAGE"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "damaged_or_uncertain_seal" in result.exclusion_reasons


def test_weak_or_torn_seal_is_rejected():
    result = strict_match_listing(
        product("Classic Sixth Edition - Booster Box"),
        listing("MTG Classic Sixth Edition Sealed Booster Box WOTC Seal Weak/Torn"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "damaged_or_uncertain_seal" in result.exclusion_reasons


def test_partial_booster_box_is_rejected():
    result = strict_match_listing(
        product("Gatecrash - Booster Box"),
        listing("Vintage Gatecrash Partial Booster Box 30 Sealed Packs MTG"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "incomplete_product" in result.exclusion_reasons


def test_theme_booster_display_is_rejected():
    result = strict_match_listing(
        product("Guilds of Ravnica - Booster Box"),
        listing("MTG Guilds of Ravnica Theme Booster Display Box Sealed 10 Jumbo Packs"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_set_booster_box_is_rejected_for_draft_box_target():
    result = strict_match_listing(
        product("Dominaria - Booster Box"),
        listing("MTG Dominaria United Set Booster Box English 30 Packs Factory Sealed"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_dominaria_variants_do_not_match_original_dominaria():
    result = strict_match_listing(
        product("Dominaria - Booster Box"),
        listing("MTG Dominaria Remastered Collector Booster Box Sealed"),
        "RUN",
        "2026-07-22T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_precision_runner_uses_strict_matcher_without_recursion(monkeypatch, tmp_path):
    sample_product = product("Amonkhet - Booster Box")

    monkeypatch.setattr(
        ebay_universe,
        "ORIGINAL_CSV_UNIVERSE",
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


def test_precision_runner_honors_explicit_universe_override(monkeypatch, tmp_path):
    selected = [
        product("Amonkhet - Booster Box"),
        CanonicalProduct(
            canonical_product_id="MTG-TEST-2",
            canonical_product_name="Kaladesh - Booster Box",
            canonical_set_name="Kaladesh",
            product_class="PRE_COLLECTOR_BOOSTER_BOX",
            tcgplayer_product_id="2",
            release_date="2016-09-30",
            ebay_query="query",
        ),
    ]
    monkeypatch.setattr(base, "OUTPUT_ROOT", tmp_path)

    class FakeClient:
        def search_product(self, product, limit=20):
            return [
                listing(
                    f"MTG Magic the Gathering {product.canonical_set_name} "
                    "Booster Box Factory Sealed"
                )
            ], 1

    monkeypatch.setattr(base, "EbayBrowseClient", FakeClient)

    summary = run_coverage(
        limit_per_product=20,
        universe_override=selected,
    )

    assert summary["products"] == 2
    assert summary["listing_rows"] == 2
