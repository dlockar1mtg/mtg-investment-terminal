from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_ebay_matching_batch.py"
INSTALLER = ROOT / "scripts/apply_ebay_fail_fast_protection.py"

BROKEN = '        print("\nEBAY MATCHING BATCH: INCOMPLETE")'
FIXED = '        print("\\nEBAY MATCHING BATCH: INCOMPLETE")'


def repair_text(text: str) -> tuple[str, int]:
    count = 0
    if BROKEN in text:
        text = text.replace(BROKEN, FIXED)
        count += 1

    lines = text.splitlines()
    repaired: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if (
            line.strip() == 'print("'
            and index + 1 < len(lines)
            and lines[index + 1].strip() == 'EBAY MATCHING BATCH: INCOMPLETE")'
        ):
            indent = line[: len(line) - len(line.lstrip())]
            repaired.append(indent + 'print("\\nEBAY MATCHING BATCH: INCOMPLETE")')
            index += 2
            count += 1
            continue
        repaired.append(line)
        index += 1

    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(repaired) + suffix, count


def main() -> None:
    changed = []
    for path in (RUNNER, INSTALLER):
        original = path.read_text(encoding="utf-8")
        repaired, count = repair_text(original)
        if count:
            path.write_text(repaired, encoding="utf-8")
            changed.append((path, count))

    if not changed:
        raise SystemExit("No broken fail-fast newline pattern was found")

    print("EBAY FAIL-FAST NEWLINE REPAIR V2: APPLIED")
    for path, count in changed:
        print(f"Updated: {path.relative_to(ROOT)} ({count} repair(s))")


if __name__ == "__main__":
    main()
