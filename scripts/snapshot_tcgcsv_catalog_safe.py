from __future__ import annotations
import argparse, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.external_discovery.snapshot_tcgcsv_catalog import snapshot_tcgcsv_products
ARCHIVE = ROOT/"data/operations/mtg_source_discovery/tcgcsv_snapshots"
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--category-id",type=int)
    ap.add_argument("--max-groups",type=int)
    ap.add_argument("--sleep-seconds",type=float,default=.1)
    a=ap.parse_args()
    m=snapshot_tcgcsv_products(category_id=a.category_id,max_groups=a.max_groups,sleep_seconds=max(0,a.sleep_seconds))
    now=datetime.now(timezone.utc); run=now.strftime("%Y%m%dT%H%M%SZ"); d=ARCHIVE/run; d.mkdir(parents=True)
    for key,name in {"products":"tcgcsv_magic_products.csv","groups":"tcgcsv_magic_groups.csv","audit":"tcgcsv_snapshot_audit.csv"}.items():
        shutil.copy2(Path(m["files"][key]["path"]),d/name)
    m=dict(m); m.update({"archive_run_id":run,"archive_directory":str(d),"archived_at_utc":now.isoformat()})
    (d/"tcgcsv_snapshot_manifest.json").write_text(json.dumps(m,indent=2),encoding="utf-8")
    print(json.dumps({"status":"PASS","run_id":run,"archive_directory":str(d),"limited_run":bool(m.get("limited_run")),"captured_product_rows":int(m.get("captured_product_rows",0))},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
