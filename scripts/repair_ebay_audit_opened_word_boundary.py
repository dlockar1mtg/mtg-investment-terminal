from __future__ import annotations

from pathlib import Path

AUDIT_PATH = Path("scripts/audit_ebay_matching_batch.py")


def apply() -> None:
    text = AUDIT_PATH.read_text(encoding="utf-8")

    old = 'r"presell|pre[- ]?sale|pre[- ]?order|pre aug|opened|empty|proxy|digital|"'
    new = 'r"presell|pre[- ]?sale|pre[- ]?order|pre aug|\\bopened\\b|empty|proxy|digital|"'

    if old in text:
        text = text.replace(old, new, 1)
    elif r"\bopened\b" in text:
        print("EBAY AUDIT OPENED WORD-BOUNDARY REPAIR: ALREADY APPLIED")
        print(f"Audit: {AUDIT_PATH}")
        return
    else:
        raise RuntimeError("Expected suspicious-title regex anchor was not found.")

    AUDIT_PATH.write_text(text, encoding="utf-8")

    print("EBAY AUDIT OPENED WORD-BOUNDARY REPAIR: APPLIED")
    print(f"Audit: {AUDIT_PATH}")
    print("Rule: opened is flagged; unopened is allowed")


if __name__ == "__main__":
    apply()
