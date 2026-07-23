from __future__ import annotations

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources import ebay_universe
from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision import run_coverage, strict_match_listing


def product(
    name: str = "Alpha Edition - Booster Box",
    product_class: str = "PRE_COLLECTOR_BOOSTER_BOX",
) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id="MTG-TEST",
        canonical_product_name=name,
        canonical_set_name=name.replace(" - Booster Box", ""),
        product_class=product_class,
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



def test_play_booster_box_is_rejected_for_historical_box():
    result = strict_match_listing(
        product("Lorwyn - Booster Box"),
        listing("MTG Lorwyn Eclipsed Play Booster Box Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_innistrad_remastered_is_rejected_for_original_innistrad():
    result = strict_match_listing(
        product("Innistrad - Booster Box"),
        listing("MTG Innistrad Remastered Collector Booster Box New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_midnight_hunt_is_rejected_for_original_innistrad():
    result = strict_match_listing(
        product("Innistrad - Booster Box"),
        listing("MTG Innistrad Midnight Hunt Collector Booster Box Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_lorwyn_eclipsed_is_rejected_for_original_lorwyn():
    result = strict_match_listing(
        product("Lorwyn - Booster Box"),
        listing("MTG Lorwyn Eclipsed Collector Booster Box Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_modern_horizons_three_is_rejected_for_original_modern_horizons():
    result = strict_match_listing(
        product("Modern Horizons - Booster Box"),
        listing("MTG Modern Horizons 3 Play Booster Box Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_ampersand_two_product_listing_is_rejected():
    result = strict_match_listing(
        product("Journey Into Nyx - Booster Box"),
        listing("Magic the Gathering Journey into Nyx & Origins Booster Boxes JP NEW SEALED"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "mixed_product_listing" in result.exclusion_reasons


def test_jp_language_marker_is_rejected():
    result = strict_match_listing(
        product("Journey Into Nyx - Booster Box"),
        listing("Magic the Gathering Journey into Nyx Booster Box *JP* NEW SEALED"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "non_english" in result.exclusion_reasons


def test_battle_pack_display_is_rejected():
    result = strict_match_listing(
        product("Return to Ravnica - Booster Box"),
        listing("MTG Return to Ravnica Battle Pack Display Box New"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_theme_deck_display_is_rejected():
    result = strict_match_listing(
        product("Scourge - Booster Box"),
        listing("MTG Scourge Theme Deck Display Box Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_theros_beyond_death_is_rejected_for_original_theros():
    result = strict_match_listing(
        product("Theros - Booster Box"),
        listing("MTG Theros Beyond Death Collector Booster Box 12 Pack English New"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_zendikar_rising_is_rejected_for_original_zendikar():
    result = strict_match_listing(
        product("Zendikar - Booster Box"),
        listing("MTG Zendikar Rising Collector Booster Box English Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "conflicting_set_identity" in result.exclusion_reasons


def test_retail_cardboard_display_is_rejected():
    result = strict_match_listing(
        product("Time Spiral - Booster Box"),
        listing("Magic the Gathering Time Spiral Booster Retail Cardboard Walmart Display Box MTG"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_box_only_listing_is_rejected():
    result = strict_match_listing(
        product("Unhinged - Booster Box"),
        listing("Magic The Gathering MTG Unhinged Booster Box Box Only"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_factory_sealed_unstable_unset_remains_accepted():
    result = strict_match_listing(
        product("Unstable - Booster Box"),
        listing("MTG Unstable Booster Box Factory Sealed Unopened Magic The Gathering Un-Set"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "ACCEPTED"


def test_plural_booster_boxes_are_rejected_as_ambiguous_multi_unit():
    result = strict_match_listing(
        product("Amonkhet - Booster Box"),
        listing("MtG Magic the Gathering Amonkhet Booster Boxes"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "ambiguous_multi_unit_listing" in result.exclusion_reasons


def test_secret_lair_nonfoil_rejects_foil_variant():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Astrology Lands Aquarius Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_foil_rejects_nonfoil_variant():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Astrology Lands Aquarius Non-Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_rejects_wrong_astrology_sign():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Astrology Lands Pisces Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_book_club_requires_book_club_identity():
    result = strict_match_listing(
        product(
            "Secret Lair Countdown Kit: An Encyclopedia of Magic Book Club Bundle",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Countdown Kit An Encyclopedia of Magic Factory Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_bundle_rejects_individual_drop_listing():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aries) Bundle - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Astrology Lands Aries Non-Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_individual_drop_rejects_bundle_listing():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aries) - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Astrology Lands Aries Non-Foil Bundle Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_exact_bundle_identity_can_be_accepted():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aries) Bundle - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Astrology Lands Aries Non-Foil Bundle Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "ACCEPTED"


def test_secret_lair_bundle_without_bundle_identity_is_rejected():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Drop Astrology Lands Aquarius Traditional Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_exact_astrology_bundle_variant_can_be_accepted():
    result = strict_match_listing(
        product(
            "Secret Lair Drop: Astrology Lands (Aquarius) Bundle - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Drop Astrology Lands Aquarius Bundle Traditional Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "ACCEPTED"

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

def test_secret_lair_presell_listing_is_rejected():
    result = strict_match_listing(
        product(
            "Reality Fracture - Secret Lair Bundle",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "Magic The Gathering Reality Fracture Secret Lair Bundle "
            "(Presell) English Factory Sealed"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "presale" in result.exclusion_reasons

def test_secret_lair_traditional_foil_rejects_explicit_rainbow_foil_listing():
    result = strict_match_listing(
        product(
            "Drop: Aether Drifters - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Aether Drifters Rainbow Foil Sealed in Hand"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_rainbow_foil_rejects_explicit_traditional_foil_listing():
    result = strict_match_listing(
        product(
            "Drop: Arcade Racers - Rainbow Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Arcade Racers Traditional Foil Edition Sealed"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_traditional_foil_allows_generic_foil_listing():
    result = strict_match_listing(
        product(
            "Drop: Absolute Annihilation - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Absolute Annihilation Foil Edition Sealed"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "ACCEPTED"


def test_secret_lair_nonfoil_rejects_mixed_rainbow_and_nonfoil_set_listing():
    result = strict_match_listing(
        product(
            "Drop: Artist Series: Kieran Yanner - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Artist Series Kieran Yanner Rainbow Foil Non Foil Set Sealed"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_nonfoil_rejects_combined_foil_nonfoil_listing():
    result = strict_match_listing(
        product(
            "Drop: Artist Series: Livia Prima - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Artist Series Livia Prima Non-Foil+Foil Edition Sealed"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_nonfoil_rejects_upick_finish_listing():
    result = strict_match_listing(
        product(
            "Drop: Artist Series: Ryan Alexander Lee - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing(
            "MTG Secret Lair Artist Series Ryan Alexander Lee Upick Foil/Non Foil SLD"
        ),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons

def test_secret_lair_cats_dogs_title_collision_is_rejected():
    result = strict_match_listing(
        product(
            "Drop: Cats Are Better Than Dogs - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Dogs Are Better Than Cats Non-Foil Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_allied_enemy_talisman_collision_is_rejected():
    result = strict_match_listing(
        product(
            "Drop: Dan Frazier Is Back Again: The Enemy Talismans - Foil Etched Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Secret Lair Dan Frazier Allied Talismans Foil Etched Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_extra_life_year_collision_is_rejected():
    result = strict_match_listing(
        product(
            "Drop: Extra Life 2022 - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Extra Life 2020 Traditional Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_kevin_eastman_colors_inks_collision_is_rejected():
    result = strict_match_listing(
        product(
            "Drop: Featuring: Kevin Eastman (Colors) - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Secret Lair Featuring Kevin Eastman Inks Traditional Foil Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_just_add_milk_second_helpings_collision_is_rejected():
    result = strict_match_listing(
        product(
            "Drop: Just Add Milk - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Just Add Milk Second Helpings Non Foil Secret Lair New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_just_add_milk_second_helpings_exact_match_is_allowed():
    result = strict_match_listing(
        product(
            "Drop: Just Add Milk: Second Helpings - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Just Add Milk Second Helpings Non Foil Secret Lair New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "ACCEPTED"


def test_secret_lair_liler_lilest_walkers_collision_is_rejected():
    result = strict_match_listing(
        product(
            "Drop: Li'l'er Walkers - Non-Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Drop Li'l'est Walkers Non Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_pixelsnowlands_generic_foil_rejects_etched_canonical():
    result = strict_match_listing(
        product(
            "Drop: PixelSnowLands.jpg - Foil Etched Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair PixelSnowLands.jpg Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_pixelsnowlands_generic_foil_rejects_traditional_canonical():
    result = strict_match_listing(
        product(
            "Drop: PixelSnowLands.jpg - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair PixelSnowLands.jpg Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_brain_dead_creatures_lands_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Brain Dead: Creatures - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("MTG Secret Lair x Brain Dead: Lands Rainbow Foil Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_arcane_base_lands_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Arcane - Traditional Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair x Arcane: Lands Traditional Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_spiderman_heroic_villainous_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Marvel's Spider-Man: Heroic Deeds - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Spider-Man Villainous Plots Rainbow Foil Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_beholder_volume_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Dungeons & Dragons: Death is in the Eyes of the Beholder II - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Dungeons & Dragons Death is in the Eyes of the Beholder I Foil"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_monty_python_volume_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Monty Python: Monty Python and the Holy Grail: Vol. 1 - Traditional Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Monty Python and the Holy Grail Vol. 2 Foil Edition Box"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_venom_colors_inks_collision_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Marvel's Spider-Man: Venom Unleashed (Colors) - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Spider-Man Venom Unleashed Inks Rainbow Foil Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_venom_generic_variant_is_rejected():
    result = strict_match_listing(
        product("Drop: Secret Lair x Marvel's Spider-Man: Venom Unleashed (Colors) - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("Secret Lair Spider-Man Venom Unleashed Foil Edition Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_twisted_metal_sol_ring_does_not_match_generic_promo():
    result = strict_match_listing(
        product("Drop: Secret Lair Promo: Sol Ring - Rainbow Foil Edition", product_class="SEALED_SECRET_LAIR"),
        listing("MTG Sol Ring Rainbow Foil Secret Lair Promo Twisted Metal Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"


def test_secret_lair_beholder_roman_two_rejects_numeric_one_listing():
    result = strict_match_listing(
        product(
            "Drop: Secret Lair x Dungeons & Dragons: Death is in the Eyes of the Beholder II - Rainbow Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("FOIL Secret Lair x Dungeons & Dragons Death Is in the Eyes of the Beholder 1"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_beholder_roman_one_allows_numeric_one_listing():
    result = strict_match_listing(
        product(
            "Drop: Secret Lair x Dungeons & Dragons: Death is in the Eyes of the Beholder I - Rainbow Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("FOIL Secret Lair x Dungeons & Dragons Death Is in the Eyes of the Beholder 1"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state != "REJECTED"


def test_secret_lair_kaldheim_part_one_rejects_part_two_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: Kaldheim - Part 1 - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Showcase Kaldheim Part 2 Foil New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_kaldheim_part_two_allows_part_two_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: Kaldheim - Part 2 - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("MTG Secret Lair Showcase Kaldheim Part 2 Foil New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state != "REJECTED"


def test_secret_lair_march_machine_volume_one_rejects_volume_two_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: March of the Machine Vol. 1 - Halo Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Showcase March of the Machine Vol. 2 Halo Foil Secret Lair Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_march_machine_volume_two_allows_volume_two_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: March of the Machine Vol. 2 - Halo Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Showcase March of the Machine Vol. 2 Halo Foil Secret Lair Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state != "REJECTED"


def test_secret_lair_read_fine_print_traditional_rejects_etched_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: Read The Fine Print - Traditional Foil Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Secret Lair Showcase Read The Fine Print Foil Etched Edition New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state == "REJECTED"
    assert "secret_lair_variant_conflict" in result.exclusion_reasons


def test_secret_lair_read_fine_print_etched_allows_etched_listing():
    result = strict_match_listing(
        product(
            "Drop: Showcase: Read The Fine Print - Foil Etched Edition",
            product_class="SEALED_SECRET_LAIR",
        ),
        listing("Secret Lair Showcase Read The Fine Print Foil Etched Edition New Sealed"),
        "RUN",
        "2026-07-23T00:00:00Z",
    )
    assert result.match_state != "REJECTED"

