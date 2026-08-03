"""Run day-one multi-product adjudication through a non-mutating schema adapter."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_hardened_replay/collector_ebay_full_universe_hardened_replay.csv"
TEMP = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_hardened_replay/collector_ebay_full_universe_hardened_replay_schema_adapted.tmp.csv"


def norm_id(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("TCGPLAYER-"):
        text = text.removeprefix("TCGPLAYER-")
    return text[:-2] if text.endswith(".0") else text


def pick_product_id_column(frame: pd.DataFrame) -> str:
    for column in (
        "resolved_tcgplayer_product_id",
        "tcgplayer_product_id",
        "canonical_product_id",
    ):
        if column in frame.columns:
            return column
    raise RuntimeError(
        "Hardened replay schema has no governed product identifier. "
        f"Available columns: {list(frame.columns)}"
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run adjudication through replay schema adapter")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--winner-margin", type=float, default=0.08)
    return p


def main() -> int:
    args = parser().parse_args()
    if not SOURCE.is_file():
        raise RuntimeError(f"Missing hardened replay source: {SOURCE}")

    frame = pd.read_csv(SOURCE, dtype=str, encoding="utf-8-sig").fillna("")
    source_column = pick_product_id_column(frame)
    frame["resolved_tcgplayer_product_id"] = frame[source_column].map(norm_id)
    TEMP.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(TEMP, index=False)

    try:
        import scripts.adjudicate_collector_ebay_day_one_multi_product_accepts as adjudication

        adjudication.REPLAY = TEMP
        sys.argv = [
            "adjudicate_collector_ebay_day_one_multi_product_accepts.py",
            "--winner-margin",
            str(args.winner_margin),
        ]
        if args.strict:
            sys.argv.append("--strict")
        return int(adjudication.main())
    finally:
        TEMP.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
