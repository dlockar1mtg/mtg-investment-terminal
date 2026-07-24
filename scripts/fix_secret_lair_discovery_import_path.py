from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    target = root / "scripts" / "discover_full_secret_lair_catalog.py"

    text = target.read_text(encoding="utf-8")

    old = (
        "import csv\n"
        "import re\n"
        "import sqlite3\n"
        "from pathlib import Path\n"
        "from typing import Iterable\n\n"
        "from terminal2.config import DB_FILE\n\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
    )
    new = (
        "import csv\n"
        "import re\n"
        "import sqlite3\n"
        "import sys\n"
        "from pathlib import Path\n"
        "from typing import Iterable\n\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "if str(ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(ROOT))\n\n"
        "from terminal2.config import DB_FILE\n"
    )

    if old not in text:
        if "sys.path.insert(0, str(ROOT))" in text:
            print("Secret Lair discovery import path is already fixed.")
            return
        raise RuntimeError("Expected import block was not found")

    target.write_text(text.replace(old, new, 1), encoding="utf-8")

    print("Secret Lair discovery import path fixed.")
    print(r"Updated: scripts\discover_full_secret_lair_catalog.py")


if __name__ == "__main__":
    main()
