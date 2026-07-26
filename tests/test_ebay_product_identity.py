from terminal2.market_sources.ebay_product_identity import evaluate_title, parse_product_identity


def test_secret_lair_bundle_finish_identity() -> None:
    identity = parse_product_identity(
        "Astrology Lands (Sagittarius) Bundle — Traditional Foil Edition",
        "SEALED_SECRET_LAIR",
    )
    assert identity.product_family == "SECRET_LAIR"
    assert identity.product_form == "BUNDLE"
    assert identity.finish == "TRADITIONAL_FOIL"

    ok, reasons, coverage = evaluate_title(
        identity,
        "MTG Secret Lair Astrology Lands Sagittarius Bundle Traditional Foil Sealed",
    )
    assert ok is True
    assert reasons == []
    assert coverage == 1.0


def test_secret_lair_bundle_rejects_wrong_finish_and_single_drop() -> None:
    identity = parse_product_identity(
        "Astrology Lands (Sagittarius) Bundle — Traditional Foil Edition",
        "SEALED_SECRET_LAIR",
    )
    ok, reasons, _ = evaluate_title(
        identity,
        "Secret Lair Astrology Lands Sagittarius single drop nonfoil sealed",
    )
    assert ok is False
    assert "missing_required_phrase:bundle" in reasons
    assert "missing_required_phrase:traditional_foil" in reasons
    assert "forbidden_phrase:non_foil" in reasons
    assert "forbidden_phrase:single_drop" in reasons


def test_booster_display_rejects_single_pack() -> None:
    identity = parse_product_identity(
        "Wilds of Eldraine Draft Booster Display",
        "PRE_COLLECTOR_BOOSTER_BOX",
    )
    ok, reasons, _ = evaluate_title(
        identity,
        "MTG Wilds of Eldraine Draft Booster single pack sealed",
    )
    assert ok is False
    assert "forbidden_phrase:single_pack" in reasons


def test_booster_display_allows_legitimate_retail_pack_count() -> None:
    identity = parse_product_identity(
        "Modern Horizons 3 Collector Booster Display",
        "COLLECTOR_BOOSTER_BOX",
    )
    ok, reasons, coverage = evaluate_title(
        identity,
        "MTG Modern Horizons 3 Collector Booster Box 12 Packs English Factory Sealed",
    )
    assert ok is True
    assert reasons == []
    assert coverage == 1.0


def test_numbered_product_identity_rejects_sibling_set() -> None:
    identity = parse_product_identity(
        "Modern Horizons 2 Collector Booster Display",
        "COLLECTOR_BOOSTER_BOX",
    )
    assert "2" in identity.required_tokens

    ok, reasons, coverage = evaluate_title(
        identity,
        "MTG Modern Horizons 3 Collector Booster Box Factory Sealed",
    )
    assert ok is False
    assert coverage < 1.0
    assert "insufficient_identity_token_coverage" in reasons


def test_commander_deck_requires_deck_form() -> None:
    identity = parse_product_identity(
        "Commander Deck: Goblin Storm — Standard Edition",
        "SEALED_SECRET_LAIR",
    )
    ok, reasons, _ = evaluate_title(identity, "Secret Lair Goblin Storm single card")
    assert ok is False
    assert "missing_required_phrase:commander_deck" in reasons
    assert "forbidden_phrase:single_card" in reasons
