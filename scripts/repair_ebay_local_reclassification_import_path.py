from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/reclassify_ebay_matching_batch.py"
TEST = ROOT / "tests/test_ebay_local_reclassification.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Expected {label} anchor not found")
    return text.replace(old, new, 1)


def apply_script_repair() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    old = '''from pathlib import Path

from terminal2.market_sources.ebay_matching import CanonicalProduct
'''
    new = '''from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_matching import CanonicalProduct
'''
    text = replace_once(text, old, new, "script import path")
    SCRIPT.write_text(text, encoding="utf-8")


def apply_test_repair() -> None:
    text = TEST.read_text(encoding="utf-8")
    marker = "def test_reclassification_script_supports_direct_execution_import_path():"
    if marker in text:
        return
    addition = r'''


def test_reclassification_script_supports_direct_execution_import_path():
    script = ROOT / "scripts/reclassify_ebay_matching_batch.py"
    text = script.read_text(encoding="utf-8")
    assert "sys.path.insert(0, str(ROOT))" in text
'''
    TEST.write_text(text + addition, encoding="utf-8")


def apply() -> None:
    apply_script_repair()
    apply_test_repair()
    print("EBAY LOCAL RECLASSIFICATION IMPORT PATH REPAIR: APPLIED")
    print(f"Updated: {SCRIPT.relative_to(ROOT)}")
    print(f"Updated: {TEST.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
