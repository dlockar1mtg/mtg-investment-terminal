"""Inventory local historical MTG sources without selecting or mutating observations."""
from __future__ import annotations
import argparse, csv, json, os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/mtg/governance/collector_historical_reconstruction_policy_v1.json"
DEFAULT_OUT = ROOT / "data/governance/permanence/certification/collector_historical_source_inventory"


def parser():
    p=argparse.ArgumentParser(description="Audit Collector historical sources")
    p.add_argument("--policy",type=Path,default=DEFAULT_POLICY)
    p.add_argument("--output-dir",type=Path,default=DEFAULT_OUT)
    p.add_argument("--strict",action="store_true")
    return p

def lowset(items): return {str(x).strip().lower() for x in items if str(x).strip()}
def first_hit(columns,candidates):
    lookup={c.lower():c for c in columns}
    return next((lookup[x.lower()] for x in candidates if x.lower() in lookup),"")
def inspect_csv(path:Path):
    with path.open("r",encoding="utf-8-sig",newline="",errors="replace") as f:
        r=csv.reader(f); header=next(r,[]); rows=sum(1 for _ in r)
    return [str(x).strip() for x in header],rows

def inspect_json(path:Path):
    obj=json.loads(path.read_text(encoding="utf-8-sig",errors="replace"))
    if isinstance(obj,list): rows=obj
    elif isinstance(obj,dict) and isinstance(obj.get("results"),list): rows=obj["results"]
    elif isinstance(obj,dict): rows=[obj]
    else: rows=[]
    cols=[]
    for row in rows[:50]:
        if isinstance(row,dict):
            for key in row:
                if key not in cols: cols.append(str(key))
    return cols,len(rows)
def main():
    a=parser().parse_args(); policy=json.loads(a.policy.resolve().read_text(encoding="utf-8-sig")); out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
    roots=[ROOT/x for x in policy["candidate_roots"]]; exts=lowset(policy["candidate_extensions"]); markers=lowset(policy["history_name_markers"])
    inventory=[]; schema=[]; candidates=[]; errors=[]
    for base in roots:
        if not base.exists(): continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in exts: continue
            rel=path.relative_to(ROOT).as_posix(); marker_hits=sorted(m for m in markers if m in rel.lower())
            if not marker_hits: continue
            try:
                cols,rows=inspect_csv(path) if path.suffix.lower()==".csv" else inspect_json(path)
                id_col=first_hit(cols,policy["identity_columns"]); name_col=first_hit(cols,policy["name_columns"]); date_col=first_hit(cols,policy["date_columns"]); price_col=first_hit(cols,policy["price_columns"])
                score=(4 if id_col else 0)+(2 if name_col else 0)+(3 if date_col else 0)+(3 if price_col else 0)+(1 if rows else 0)
                status="HIGH_PRIORITY" if score>=10 else "CANDIDATE" if score>=6 else "LOW_SIGNAL"
                stat=path.stat()
                row={"path":rel,"extension":path.suffix.lower(),"size_bytes":stat.st_size,"modified_utc":datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat(),"row_count":rows,"column_count":len(cols),"marker_hits":";".join(marker_hits),"identity_column":id_col,"name_column":name_col,"date_column":date_col,"price_column":price_col,"evidence_score":score,"candidate_status":status}
                inventory.append(row)
                for c in cols: schema.append({"path":rel,"column_name":c})
                if status!="LOW_SIGNAL": candidates.append(row)
            except Exception as e:
                errors.append({"path":rel,"error_type":type(e).__name__,"error_message":str(e)[:500]})
    inventory.sort(key=lambda r:(-int(r["evidence_score"]),r["path"])); candidates.sort(key=lambda r:(-int(r["evidence_score"]),r["path"]))
    def write(name,rows,fields):
        with (out/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    inv_fields=["path","extension","size_bytes","modified_utc","row_count","column_count","marker_hits","identity_column","name_column","date_column","price_column","evidence_score","candidate_status"]
    write("collector_history_source_inventory.csv",inventory,inv_fields)
    write("collector_history_schema_inventory.csv",schema,["path","column_name"])
    write("collector_history_candidate_sources.csv",candidates,inv_fields)
    write("collector_history_source_errors.csv",errors,["path","error_type","error_message"])
    summary={"audit_name":"Collector Historical Source Inventory","audit_version":"1.0.1","generated_at":datetime.now(timezone.utc).isoformat(),"files_profiled":len(inventory),"candidate_sources":len(candidates),"high_priority_sources":sum(r["candidate_status"]=="HIGH_PRIORITY" for r in candidates),"source_errors":len(errors),"fixed_product_count_assumed":False,"historical_selection_executed":False,"historical_append_authorized":False,"forecasting_resume_authorized":False,"purchase_recommendation_authorized":False,"status":"PASS_SOURCE_INVENTORY" if candidates else "REVIEW_REQUIRED"}
    (out/"collector_history_inventory_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8"); print(json.dumps(summary,indent=2))
    return 1 if a.strict and (not candidates or errors) else 0
if __name__=="__main__": raise SystemExit(main())
