from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/run_ebay_matching_batch.py"
INSTALLER_PATH = ROOT / "scripts/apply_ebay_fail_fast_protection.py"


def repair_runner(text: str) -> str:
    broken = '        print("\nEBAY MATCHING BATCH: INCOMPLETE")'
    if broken in text:
        return text

    split_literal = '        print("\nEBAY MATCHING BATCH: INCOMPLETE")'.replace('\\n', '\n')
    if split_literal not in text:
        raise RuntimeError("Expected broken fail-fast print statement was not found")
    return text.replace(split_literal, broken, 1)


def repair_installer(text: str) -> str:
    old = '        print("\\nEBAY MATCHING BATCH: INCOMPLETE")'
    new = '        print("\\\\nEBAY MATCHING BATCH: INCOMPLETE")'
    if new in text:
        return text
    if old not in text:
        raise RuntimeError("Expected installer newline literal was not found")
    return text.replace(old, new, 1)


def main() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    RUNNER_PATH.write_text(repair_runner(runner), encoding="utf-8")

    installer = INSTALLER_PATH.read_text(encoding="utf-8")
    INSTALLER_PATH.write_text(repair_installer(installer), encoding="utf-8")

    print("EBAY FAIL-FAST NEWLINE REPAIR: APPLIED")
    print(f"Updated: {RUNNER_PATH.relative_to(ROOT)}")
    print(f"Updated: {INSTALLER_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
