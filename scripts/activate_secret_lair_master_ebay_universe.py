from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "terminal2/market_sources/ebay_matching.py"
BACKUP_ROOT = ROOT / "data/validation/phase_10/premium_universe_eligibility/activation_backups"

OLD_SOURCE = 'SECRET_LAIR_SOURCE = ROOT / "data/validation/phase_10/premium_universe_eligibility/secret_lair_structural_candidates_2026-07-22.csv"'
NEW_SOURCE = 'SECRET_LAIR_SOURCE = ROOT / "data/validation/phase_10/premium_universe_eligibility/secret_lair_master_registry_ready_universe.csv"'

OLD_BLOCK = '''    for row in _read_csv(SECRET_LAIR_SOURCE):
        name = _clean(row.get("canonical_product_name"))
        product_id = _clean(row.get("canonical_product_id"))
        if not product_id or not name:
            continue
        text = _norm(" ".join(_clean(row.get(key)) for key in (
            "canonical_product_class", "canonical_product_family",
            "canonical_product_type", "canonical_packaging_level", name,
        )))
        if " secret lair " not in text:
            continue
        products[product_id] = CanonicalProduct(
            product_id,
            name,
            _clean(row.get("canonical_set_name")),
            "SEALED_SECRET_LAIR",
            _clean(row.get("tcgplayer_product_id")),
            "",
            build_query(name, "SEALED_SECRET_LAIR"),
        )
'''

NEW_BLOCK = '''    for row in _read_csv(SECRET_LAIR_SOURCE):
        # The certified master export uses Secret Lair-native field names.
        # Legacy aliases remain supported so historical snapshots can still load.
        governance_status = _clean(row.get("governance_status")).upper()
        ebay_allowed = _clean(row.get("ebay_matching_allowed")).lower()
        if governance_status and governance_status != "REGISTRY_READY":
            continue
        if ebay_allowed and ebay_allowed not in {"true", "1", "yes"}:
            continue

        name = _clean(row.get("product_name") or row.get("canonical_product_name"))
        product_id = _clean(row.get("secret_lair_id") or row.get("canonical_product_id"))
        tcgplayer_product_id = _clean(row.get("tcgplayer_product_id"))
        set_name = _clean(
            row.get("superdrop_name")
            or row.get("drop_name")
            or row.get("canonical_set_name")
        )
        if not product_id or not name or not tcgplayer_product_id:
            continue

        # Master release_date currently contains source-publication timestamps for
        # many TCGCSV records, so it is intentionally not used for age analytics.
        products[product_id] = CanonicalProduct(
            product_id,
            name,
            set_name,
            "SEALED_SECRET_LAIR",
            tcgplayer_product_id,
            "",
            build_query(name, "SEALED_SECRET_LAIR"),
        )
'''


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)

    text = TARGET.read_text(encoding="utf-8")
    if NEW_SOURCE in text and NEW_BLOCK in text:
        print("Secret Lair master eBay universe is already active.")
        print(f"Target: {TARGET.relative_to(ROOT)}")
        return

    if OLD_SOURCE not in text:
        raise RuntimeError("Expected legacy SECRET_LAIR_SOURCE declaration was not found.")
    if OLD_BLOCK not in text:
        raise RuntimeError("Expected legacy Secret Lair build_universe block was not found.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_ROOT / f"ebay_matching_before_master_activation_{timestamp}.py"
    backup.write_text(text, encoding="utf-8")

    updated = text.replace(OLD_SOURCE, NEW_SOURCE, 1).replace(OLD_BLOCK, NEW_BLOCK, 1)
    TARGET.write_text(updated, encoding="utf-8")

    print("SECRET LAIR MASTER EBAY UNIVERSE: ACTIVATED")
    print(f"Target: {TARGET.relative_to(ROOT)}")
    print(f"Backup: {backup.relative_to(ROOT)}")
    print("Source: secret_lair_master_registry_ready_universe.csv")
    print("Expected governed Secret Lair rows: 993")


if __name__ == "__main__":
    main()
