from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_ebay_matching_batch",
    ROOT / "scripts/audit_ebay_matching_batch.py",
)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def accepted_row(canonical: str, title: str) -> dict[str, str]:
    return {
        "match_state": "ACCEPTED",
        "canonical_product_name": canonical,
        "title": title,
        "exclusion_reasons": "",
        "match_score": "0.90",
    }


def test_hyphen_spaced_nonfoil_does_not_trigger_positive_foil_exception():
    reasons = AUDIT.flag_row(
        accepted_row(
            "x Warhammer Age of Sigmar - Non-Foil Edition",
            "MTG Secret Lair x Warhammer Age of Sigmar -Non- Foil Edition Sealed",
        ),
        0.82,
    )
    assert "nonfoil_canonical_with_positive_foil_title" not in reasons


def test_true_positive_foil_title_still_triggers_for_nonfoil_canonical():
    reasons = AUDIT.flag_row(
        accepted_row(
            "x NALAC Drop: Nuestra Magia — Nonfoil Edition",
            "MTG Secret Lair Nuestra Magia Rainbow Foil Sealed",
        ),
        0.82,
    )
    assert "nonfoil_canonical_with_positive_foil_title" in reasons



def test_compact_nonfoil_canonical_is_recognized_as_nonfoil():
    reasons = AUDIT.flag_row(
        accepted_row(
            "x NALAC Drop: Nuestra Magia — Nonfoil Edition",
            "MTG Secret Lair Nuestra Magia Nonfoil Edition Sealed",
        ),
        0.82,
    )
    assert "nonfoil_canonical_with_positive_foil_title" not in reasons
