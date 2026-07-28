from __future__ import annotations
import argparse, csv, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "validation" / "phase_10" / "ebay_matching" / "production_refresh" / "full_model_evaluation"
REQUIRED = {"canonical_product_id","canonical_product_name","quality_decision","market_value_usd","observation_count","seller_count"}

def read(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def discover() -> Path:
    found = []
    for path in (ROOT / "data").rglob("*.csv"):
        if "full_model_evaluation" in str(path).lower():
            continue
        try:
            rows = read(path)
            if len(rows) != 973:
                continue
            if not rows or not REQUIRED.issubset(rows[0]):
                continue
            ids = {str(r.get("canonical_product_id","")).strip() for r in rows}
            if len(ids) != 973 or "" in ids:
                continue
            found.append((path.stat().st_mtime, path))
        except Exception:
            continue
    if not found:
        raise RuntimeError("No unique 973-row Secret Lair admission ledger was found.")
    found.sort(reverse=True)
    print(f"Selected Secret Lair ledger: {found[0][1]}")
    return found[0][1]

def run(*args: str) -> None:
    print("\n>", " ".join(args))
    cp = subprocess.run(args, cwd=ROOT)
    if cp.returncode:
        raise SystemExit(cp.returncode)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    ledger = args.ledger.resolve() if args.ledger else discover()
    run(sys.executable, "scripts/build_full_secret_lair_model_evaluation.py", "--admission-ledger", str(ledger), "--output-root", str(OUTPUT))
    manifest = json.loads((OUTPUT / "secret_lair_full_model_evaluation_manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "CERTIFIED":
        raise RuntimeError("Secret Lair producer did not certify.")
    run(sys.executable, "scripts/build_unified_mtg_intelligence.py")
    run(sys.executable, "scripts/build_phase_10_10_universal_export.py")
    run(sys.executable, "scripts/build_mtg_hosted_uip_delivery.py")
    run(sys.executable, "scripts/certify_phase_8_2_1c_2_secret_lair_semantics.py")
    print("\nPHASE 8.2.1C.2 REBUILD CHAIN: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
