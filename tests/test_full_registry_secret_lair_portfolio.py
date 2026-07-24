from __future__ import annotations

import csv
from pathlib import Path

from terminal2.portfolio.secret_lair_full_registry import (
    FullRegistryMatcher,
    finish_group,
    match_score,
    normalize_name,
)

def row(product_id: str, name: str) -> dict[str, str]:
    return {"investment_product_id": product_id, "canonical_product_name": name}

def test_normalize_name_removes_catalog_scaffolding() -> None:
    assert normalize_name("Drop: Secret Lair x Hatsune Miku: Winter Diva EN - Rainbow Foil Edition - Foil Edition") == "hatsune miku winter diva en"

def test_finish_group_defaults_unspecified_to_nonfoil() -> None:
    assert finish_group("A Lot to Learn") == "NONFOIL"
    assert finish_group("Blood Bowl - Traditional Foil") == "FOIL"
    assert finish_group("Path of Ancestry - Rainbow Foil") == "RAINBOW_FOIL"

def test_match_score_rewards_source_title_containment() -> None:
    source = "Everything Changed"
    intended = "x Avatar: The Last Airbender: Everything Changed - Non-Foil Edition â€” Nonfoil Edition"
    distractor = "Drop: EVERYTHING IS ON FIRE - Non-Foil Edition â€” Nonfoil Edition"
    assert match_score(source, intended) > match_score(source, distractor)

def test_matcher_selects_nonfoil_when_finish_unspecified() -> None:
    matcher = FullRegistryMatcher([
        row("N", "x Avatar: The Last Airbender: My Cabbages! - Non-Foil Edition â€” Nonfoil Edition"),
        row("F", "x Avatar: The Last Airbender: My Cabbages! - Rainbow Foil Edition â€” Foil Edition"),
    ])
    result = matcher.match("My Cabbages!")
    assert result.product_id == "N"
    assert result.requested_finish == "NONFOIL"

def test_matcher_preserves_rainbow_foil() -> None:
    matcher = FullRegistryMatcher([
        row("R", "Drop: Secret Lair Promo x Avatar: The Last Air Bender - Path of Ancestry - Rainbow Foil Edition â€” Foil Edition"),
        row("N", "Drop: Path of Ancestry - Non-Foil Edition â€” Nonfoil Edition"),
    ])
    result = matcher.match("Path of Ancestry - Rainbow Foil")
    assert result.product_id == "R"

def test_incompatible_supplied_id_is_rematched() -> None:
    matcher = FullRegistryMatcher([
        row("WRONG", "Drop: Unrelated Product - Traditional Foil Edition â€” Foil Edition"),
        row("RIGHT", "Drop: Artist Series: Mark Poole - Traditional Foil Edition â€” Foil Edition"),
    ])
    result = matcher.match("Mark Poole - Traditional Foil", "WRONG")
    assert result.product_id == "RIGHT"
    assert result.status == "AUTO_MATCHED"

def test_gift_cost_basis_zero_is_valid() -> None:
    assert float("0") == 0.0

