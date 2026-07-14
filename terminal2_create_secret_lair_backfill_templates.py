from pathlib import Path
import shutil

from terminal2.config import ROOT_DIR
from terminal2.secret_lair.backfill.sources import (
    MATCH_OVERRIDES_PATH,
    SOURCE_CATALOG_PATH,
    SOURCE_PRICES_PATH,
)


def _copy(template_name: str, destination: Path) -> Path:
    source = (
        Path(ROOT_DIR)
        / "data"
        / "templates"
        / template_name
    )
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination


def main():
    catalog = _copy(
        "secret_lair_source_catalog_template.csv",
        SOURCE_CATALOG_PATH,
    )
    prices = _copy(
        "secret_lair_source_prices_template.csv",
        SOURCE_PRICES_PATH,
    )
    overrides = _copy(
        "secret_lair_match_overrides_template.csv",
        MATCH_OVERRIDES_PATH,
    )

    print("Secret Lair backfill templates ready:")
    print(f"Catalog: {catalog}")
    print(f"Prices: {prices}")
    print(f"Overrides: {overrides}")


if __name__ == "__main__":
    main()
