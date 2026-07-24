from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts/audit_ebay_matching_batch.py"
TESTS = ROOT / "tests/test_ebay_audit_precision.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Expected {label} anchor not found")
    return text.replace(old, new, 1)


def apply() -> None:
    audit_text = AUDIT.read_text(encoding="utf-8")
    old_pattern = '    nonfoil_pattern = r"\\bnon(?:\\s*-\\s*|\\s+)foil\\b"\n'
    new_pattern = '    nonfoil_pattern = r"\\bnon(?:foil|\\s*-\\s*foil|\\s+foil)\\b"\n'
    audit_text = replace_once(
        audit_text,
        old_pattern,
        new_pattern,
        "nonfoil regex",
    )
    AUDIT.write_text(audit_text, encoding="utf-8")

    tests_text = TESTS.read_text(encoding="utf-8")
    marker = "def test_compact_nonfoil_canonical_is_recognized_as_nonfoil():"
    if marker not in tests_text:
        tests_text += r'''


def test_compact_nonfoil_canonical_is_recognized_as_nonfoil():
    reasons = AUDIT.flag_row(
        accepted_row(
            "x NALAC Drop: Nuestra Magia — Nonfoil Edition",
            "MTG Secret Lair Nuestra Magia Nonfoil Edition Sealed",
        ),
        0.82,
    )
    assert "nonfoil_canonical_with_positive_foil_title" not in reasons
'''
        TESTS.write_text(tests_text, encoding="utf-8")

    print("EBAY AUDIT NONFOIL REGEX REPAIR: APPLIED")
    print(f"Updated: {AUDIT.relative_to(ROOT)}")
    print(f"Updated: {TESTS.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
