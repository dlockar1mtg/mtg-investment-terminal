from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "promote_ebay_reclassification",
    ROOT / "scripts/promote_ebay_reclassification.py",
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_primary_patterns_cover_expected_outputs():
    assert len(MOD.PRIMARY_PATTERNS) == 5
    assert "ebay_listing_match_results_*.csv" in MOD.PRIMARY_PATTERNS


def test_sha256_is_stable(tmp_path: Path):
    path = tmp_path / "x.txt"
    path.write_text("abc", encoding="utf-8")
    assert MOD.sha256(path) == MOD.sha256(path)


def test_one_requires_exactly_one_match(tmp_path: Path):
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    assert MOD.one(tmp_path, "*.csv").name == "a.csv"
