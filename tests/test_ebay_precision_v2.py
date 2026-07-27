from __future__ import annotations

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision_v2 import identity_match_listing


def product(name: str, product_class: str = "COLLECTOR_BOOSTER_BOX") -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id="TEST",
        canonical_product_name=name,
        canonical_set_name=name,
        product_class=product_class,
        tcgplayer_product_id="1",
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


def classify(name: str, title: str, product_class: str = "COLLECTOR_BOOSTER_BOX"):
    return identity_match_listing(
        product(name, product_class),
        listing(title),
        "RUN",
        "2026-07-26T00:00:00Z",
    )


def test_complete_four_pack_collector_display_is_not_rejected_as_incomplete() -> None:
    result = classify(
        "Commander Masters - Collector Booster Box",
        "MTG Commander Masters Collector Booster Box 4 Packs English Factory Sealed",
    )
    assert result.match_state != "REJECTED"
    assert "incomplete_pack_box_lot" not in result.exclusion_reasons


def test_complete_twelve_pack_collector_display_is_not_rejected_as_incomplete() -> None:
    result = classify(
        "Modern Horizons 3 - Collector Booster Display",
        "MTG Modern Horizons 3 Collector Booster Box 12 Packs English Factory Sealed",
    )
    assert result.match_state != "REJECTED"
    assert "incomplete_pack_box_lot" not in result.exclusion_reasons


def test_complete_thirty_six_pack_draft_display_is_not_rejected_as_incomplete() -> None:
    result = classify(
        "Wilds of Eldraine Draft Booster Display",
        "MTG Wilds of Eldraine Draft Booster Box 36 Packs Factory Sealed",
        "PRE_COLLECTOR_BOOSTER_BOX",
    )
    assert "incomplete_pack_box_lot" not in result.exclusion_reasons


def test_partial_pack_plus_box_lot_remains_rejected() -> None:
    result = classify(
        "Chronicles - Booster Box",
        "Magic Chronicles Booster Box lot of 26 packs plus box",
        "PRE_COLLECTOR_BOOSTER_BOX",
    )
    assert result.match_state == "REJECTED"
    assert "incomplete_pack_box_lot" in result.exclusion_reasons


def test_single_pack_remains_rejected() -> None:
    result = classify(
        "Edge of Eternities - Collector Booster Display",
        "MTG Edge of Eternities Collector Booster Box Sealed 1 Pack",
    )
    assert result.match_state == "REJECTED"
    assert "single_pack_collector_product" in result.exclusion_reasons


def test_missing_secret_lair_finish_routes_to_review() -> None:
    result = classify(
        "Artist Series: Example — Traditional Foil Edition",
        "MTG Secret Lair Artist Series Example Sealed",
        "SEALED_SECRET_LAIR",
    )
    assert result.match_state == "REVIEW"
    assert "missing_required_phrase:traditional_foil" in result.exclusion_reasons
    assert "missing_identity_qualifier_requires_review" in result.exclusion_reasons


def test_explicit_opposite_secret_lair_finish_is_rejected() -> None:
    result = classify(
        "Artist Series: Example — Traditional Foil Edition",
        "MTG Secret Lair Artist Series Example Nonfoil Sealed",
        "SEALED_SECRET_LAIR",
    )
    assert result.match_state == "REJECTED"
    assert "forbidden_phrase:non_foil" in result.exclusion_reasons


def test_matching_secret_lair_finish_can_remain_accepted() -> None:
    result = classify(
        "Artist Series: Example — Traditional Foil Edition",
        "MTG Secret Lair Artist Series Example Traditional Foil Sealed",
        "SEALED_SECRET_LAIR",
    )
    assert result.match_state == "ACCEPTED"


def test_missing_bundle_word_repairs_legacy_variant_conflict_to_review() -> None:
    result = classify(
        "Astrology Lands (Sagittarius) Bundle — Traditional Foil Edition",
        "MTG Secret Lair Astrology Lands Sagittarius Traditional Foil Sealed",
        "SEALED_SECRET_LAIR",
    )
    assert result.match_state == "REVIEW"
    assert "secret_lair_variant_conflict" not in result.exclusion_reasons
    assert "missing_required_phrase:bundle" in result.exclusion_reasons
    assert "legacy_variant_conflict_repaired_to_review" in result.exclusion_reasons


def test_explicit_wrong_finish_still_rejects_secret_lair_bundle() -> None:
    result = classify(
        "Astrology Lands (Sagittarius) Bundle — Traditional Foil Edition",
        "MTG Secret Lair Astrology Lands Sagittarius Bundle Nonfoil Sealed",
        "SEALED_SECRET_LAIR",
    )
    assert result.match_state == "REJECTED"
    assert "forbidden_phrase:non_foil" in result.exclusion_reasons


def test_individual_drop_does_not_match_bundle_target() -> None:
    result = classify(
        "Astrology Lands (Sagittarius) Bundle — Traditional Foil Edition",
        "MTG Secret Lair Astrology Lands Sagittarius single drop Traditional Foil Sealed",
        "SEALED_SECRET_LAIR",
    )
    assert result.match_state == "REJECTED"
    assert "forbidden_phrase:single_drop" in result.exclusion_reasons


def test_japanese_target_accepts_matching_japanese_collector_box() -> None:
    result = classify(
        "FINAL FANTASY - Collector Booster Display (Japanese)",
        "Magic The Gathering FINAL FANTASY Japanese Collector Booster Box Factory Sealed",
    )
    assert result.match_state == "ACCEPTED"
    assert "non_english" not in result.exclusion_reasons
    assert "language_match:japanese" in result.exclusion_reasons
    assert "governed_language_variant" in result.exclusion_reasons


def test_japanese_target_rejects_explicit_english_collector_box() -> None:
    result = classify(
        "FINAL FANTASY - Collector Booster Display (Japanese)",
        "MTG Final Fantasy Collector Booster Box English Sealed",
    )
    assert result.match_state == "REJECTED"
    assert "language_variant_conflict" in result.exclusion_reasons
    assert "expected_language:japanese" in result.exclusion_reasons
    assert "observed_language:english" in result.exclusion_reasons


def test_japanese_target_without_language_marker_routes_to_review() -> None:
    result = classify(
        "FINAL FANTASY - Collector Booster Display (Japanese)",
        "MTG Final Fantasy Collector Booster Box Factory Sealed",
    )
    assert result.match_state == "REVIEW"
    assert "missing_required_language:japanese" in result.exclusion_reasons
    assert "language_variant_requires_review" in result.exclusion_reasons


def test_japanese_value_booster_remains_rejected_for_wrong_form() -> None:
    result = classify(
        "FINAL FANTASY - Collector Booster Display (Japanese)",
        "Magic The Gathering Final Fantasy Value Booster 10 Pack Sealed Box Japanese",
    )
    assert result.match_state == "REJECTED"
    assert "loose_packs" in result.exclusion_reasons or "excluded_product_form" in result.exclusion_reasons
