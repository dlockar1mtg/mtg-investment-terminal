from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision_v3 import identity_match_listing
from terminal2.market_sources.ebay_universal_classification import (
    detect_multi_display_quantity,
    detect_quantity,
)


def product(product_id: str = "484912") -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id=f"TCGPLAYER-{product_id}",
        canonical_product_name="Universes Beyond: The Lord of the Rings: Tales of Middle-earth Collector Booster Display",
        canonical_set_name="LTR",
        product_class="COLLECTOR_BOOSTER_BOX",
        tcgplayer_product_id=product_id,
        release_date="2023-06-23",
        ebay_query="",
    )


def match(title: str):
    return identity_match_listing(product(), {"itemId": "test", "title": title}, "TEST", "2026-08-02T00:00:00+00:00")


def test_release_year_is_not_quantity() -> None:
    assert detect_quantity("Double Masters 2022 Booster Box Factory Sealed") is None
    assert detect_quantity("Double Masters 2020 Booster Box New Sealed") is None


def test_explicit_multi_display_quantity_is_detected() -> None:
    assert detect_quantity("Collector Booster Box X2") == 2
    assert detect_quantity("2x Collector Booster Boxes") == 2
    assert detect_multi_display_quantity("Collector Booster Box X2") == 2
    assert detect_multi_display_quantity("2x Collector Booster Boxes") == 2
    assert detect_multi_display_quantity("2 x Magic the Gathering Marvel Super Heroes Collector Booster Box") == 2
    assert detect_multi_display_quantity("2 × MTG Collector Booster Box") == 2


def test_retail_pack_count_is_not_multi_display_quantity() -> None:
    assert detect_quantity("Collector Booster Box 12 Packs") == 12
    assert detect_multi_display_quantity("Collector Booster Box 12 Packs") is None
    result = match("MTG Lord of the Rings Tales of Middle-earth Collector Booster Box (12 Packs)")
    assert result.match_state == "REVIEW"
    assert "universal_quantity_conflict:multi_display_listing" not in result.exclusion_reasons


def test_lotr_governed_alias_accepts_standard_display() -> None:
    result = match("MTG Lord of the Rings Tales of Middle-earth Collector Booster Box Sealed")
    assert result.match_state == "ACCEPTED"
    assert "governed_product_alias_applied" in result.exclusion_reasons


def test_lotr_case_remains_rejected() -> None:
    result = match("Magic Lord of the Rings Tales of Middle-earth Collector Booster Display CASE Sealed")
    assert result.match_state == "REJECTED"


def test_lotr_japanese_remains_not_accepted() -> None:
    result = match("MTG Lord of the Rings Tales of Middle-earth Collector Booster Box Sealed JPN")
    assert result.match_state != "ACCEPTED"


def test_multi_display_listing_rejected() -> None:
    result = match("MTG Lord of the Rings Tales of Middle-earth Collector Booster Box Sealed X2")
    assert result.match_state == "REJECTED"
    assert "universal_quantity_conflict:multi_display_listing" in result.exclusion_reasons


def test_spaced_multi_display_listing_rejected() -> None:
    result = match("2 x Magic the Gathering Lord of the Rings Collector Booster Box Sealed")
    assert result.match_state == "REJECTED"
    assert "universal_quantity_conflict:multi_display_listing" in result.exclusion_reasons
