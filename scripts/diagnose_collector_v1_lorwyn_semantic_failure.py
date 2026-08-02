from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_canonical_identity_lineage_recertification"
SEMANTIC = OUTPUT / "collector_lorwyn_pre_simulation_semantic_certification.json"
AUTHORITY = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_final_current_price_authority.csv"
RELEASE = ROOT / "data/governance/permanence/certification/collector_v1_wizards_release_date_authority/collector_wizards_release_date_authority.csv"
COMPARABLE = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_comparable_pool_certification.csv"
HISTORY = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger/collector_august1_historical_observation_ledger.csv"
LORWYN_ID = "MTG-CANON-TCGPLAYER-656322"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    required = [SEMANTIC, AUTHORITY, RELEASE, COMPARABLE, HISTORY]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print("MISSING REQUIRED FILES:")
        for path in missing:
            print("  " + path)
        return 1

    semantic = json.loads(SEMANTIC.read_text(encoding="utf-8"))
    authority_rows = [row for row in read_csv(AUTHORITY) if row.get("canonical_product_id") == LORWYN_ID]
    release_rows = [row for row in read_csv(RELEASE) if row.get("canonical_product_id") == LORWYN_ID]
    comparable_rows = [row for row in read_csv(COMPARABLE) if row.get("target_canonical_product_id") == LORWYN_ID]
    history_counts: dict[str, int] = {}
    for row in read_csv(HISTORY):
        canonical_id = row.get("canonical_product_id", "")
        history_counts[canonical_id] = history_counts.get(canonical_id, 0) + 1

    print("\n============================================================")
    print("LORWYN SEMANTIC CERTIFICATION")
    print("============================================================")
    print(json.dumps(semantic, indent=2))

    print("\n============================================================")
    print("LORWYN AUTHORITY ROW")
    print("============================================================")
    print(json.dumps(authority_rows, indent=2))

    print("\n============================================================")
    print("LORWYN RELEASE ROW")
    print("============================================================")
    print(json.dumps(release_rows, indent=2))

    print("\n============================================================")
    print("CERTIFIED LORWYN COMPARABLES")
    print("============================================================")
    for row in comparable_rows:
        comparable_id = row.get("comparable_canonical_product_id", "")
        print(
            {
                "rank": row.get("comparable_rank"),
                "comparable_id": comparable_id,
                "comparable_name": row.get("comparable_product_name"),
                "certification_status": row.get("certification_status"),
                "declared_observations": row.get("comparable_observation_count"),
                "ledger_observations": history_counts.get(comparable_id, 0),
                "selection_basis": row.get("selection_basis"),
            }
        )

    with_history = sum(
        history_counts.get(row.get("comparable_canonical_product_id", ""), 0) >= 2
        for row in comparable_rows
    )
    print("\nComparable rows:", len(comparable_rows))
    print("Comparables with at least 2 ledger observations:", with_history)
    print("\nNo files were modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
