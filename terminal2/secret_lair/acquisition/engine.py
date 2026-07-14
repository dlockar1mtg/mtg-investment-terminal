from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import pandas as pd
from terminal2.config import ROOT_DIR
from .config import SOURCE_CONFIG_PATH, load_source_config, parse_mapping
from .connectors import get_connector
from .normalize import normalize_catalog, normalize_prices

@dataclass(frozen=True)
class AcquisitionBuildResult:
    datasets: dict[str,pd.DataFrame]
    source_config_exists: bool

SOURCE_STAGE_ROOT=Path(ROOT_DIR)/"data"/"terminal2"/"secret_lair_acquisition_stage"

def _conflict_id(parts: str) -> str: return "SLC"+hashlib.sha1(parts.encode()).hexdigest()[:12].upper()

def _conflicts(catalog: pd.DataFrame) -> pd.DataFrame:
    cols=["conflict_id","conflict_type","source_name","source_record_id","field_name","message"]
    rows=[]
    if catalog.empty: return pd.DataFrame(columns=cols)
    for _,r in catalog.iterrows():
        for field in ("source_record_id","drop_name","variant_name","finish"):
            if not str(r.get(field,"")).strip():
                msg=f"Required acquisition field '{field}' is missing."
                rows.append({"conflict_id":_conflict_id(f"{r.get('source_name')}|{r.get('source_record_id')}|{field}|{msg}"),"conflict_type":"missing_required_field","source_name":r.get("source_name"),"source_record_id":r.get("source_record_id"),"field_name":field,"message":msg})
    dup=catalog[catalog.duplicated(["source_name","source_record_id"],keep=False)]
    for _,r in dup.iterrows():
        msg="Duplicate source identity appears more than once."
        rows.append({"conflict_id":_conflict_id(f"dup|{r['source_name']}|{r['source_record_id']}"),"conflict_type":"duplicate_source_identity","source_name":r["source_name"],"source_record_id":r["source_record_id"],"field_name":"source_record_id","message":msg})
    return pd.DataFrame(rows,columns=cols).drop_duplicates("conflict_id")

def acquire_secret_lair_sources(source_config_path: Path=SOURCE_CONFIG_PATH) -> AcquisitionBuildResult:
    config,exists=load_source_config(source_config_path)
    started=datetime.now(timezone.utc); run_id=started.strftime("SLA%Y%m%dT%H%M%S%f")
    catalogs=[]; prices=[]; logs=[]; source_status=[]
    for _,source in config.sort_values(["priority","source_name"]).iterrows():
        if not bool(source["enabled"]):
            source_status.append({**source.to_dict(),"status":"disabled","catalog_rows":0,"price_rows":0}); continue
        row_start=datetime.now(timezone.utc); status="success"; error=""; cat=pd.DataFrame(); pr=pd.DataFrame()
        try:
            connector=get_connector(str(source["connector_type"])); location=Path(str(source["location"])).expanduser()
            if not location.is_absolute(): location=Path(ROOT_DIR)/location
            result=connector.load(location)
            stamp=datetime.now(timezone.utc).isoformat()
            cat=normalize_catalog(result.catalog,str(source["source_name"]),parse_mapping(source["catalog_mapping_json"]),stamp)
            pr=normalize_prices(result.prices,str(source["source_name"]),parse_mapping(source["price_mapping_json"]),stamp,str(source["default_currency"]))
            catalogs.append(cat); prices.append(pr)
        except Exception as exc:
            status="failed"; error=str(exc)
        completed=datetime.now(timezone.utc)
        logs.append({"run_id":run_id,"source_name":source["source_name"],"started_at_utc":row_start.isoformat(),"completed_at_utc":completed.isoformat(),"status":status,"catalog_rows":len(cat),"price_rows":len(pr),"error_message":error})
        source_status.append({**source.to_dict(),"status":status,"catalog_rows":len(cat),"price_rows":len(pr),"error_message":error})
    catalog=pd.concat(catalogs,ignore_index=True) if catalogs else pd.DataFrame(columns=["source_name","source_record_id","drop_name","variant_name","finish","acquired_at_utc"])
    price=pd.concat(prices,ignore_index=True) if prices else pd.DataFrame(columns=["source_name","source_record_id","observation_date","market_price","acquired_at_utc"])
    conflicts=_conflicts(catalog)
    coverage=[]
    for row in source_status:
        src=row["source_name"]; c=catalog[catalog["source_name"].eq(src)] if not catalog.empty else catalog; p=price[price["source_name"].eq(src)] if not price.empty else price
        usable_c=int((c.get("source_record_id",pd.Series(dtype=str)).astype(str).str.strip().ne("") & c.get("drop_name",pd.Series(dtype=str)).astype(str).str.strip().ne("") & c.get("variant_name",pd.Series(dtype=str)).astype(str).str.strip().ne("") & c.get("finish",pd.Series(dtype=str)).astype(str).str.strip().ne("")).sum()) if len(c) else 0
        usable_p=int((pd.to_numeric(p.get("market_price",pd.Series(dtype=float)),errors="coerce")>0).sum()) if len(p) else 0
        denom=max(len(c)+len(p),1); score=round((usable_c+usable_p)/denom*100,2)
        coverage.append({"source_name":src,"catalog_rows":len(c),"price_rows":len(p),"usable_catalog_rows":usable_c,"usable_price_rows":usable_p,"completeness_score":score,"status":row["status"]})
    coverage=pd.DataFrame(coverage,columns=["source_name","catalog_rows","price_rows","usable_catalog_rows","usable_price_rows","completeness_score","status"])
    sources=pd.DataFrame(source_status)
    required=["source_name","connector_type","location","enabled","priority","source_quality","status"]
    for c in required:
        if c not in sources.columns: sources[c]=pd.NA
    logs=pd.DataFrame(logs,columns=["run_id","source_name","started_at_utc","completed_at_utc","status","catalog_rows","price_rows","error_message"])
    success=int((sources["status"]=="success").sum()) if not sources.empty else 0; enabled=int(sources.get("enabled",pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not sources.empty else 0
    summary=pd.DataFrame([{"snapshot_date":started.date().isoformat(),"enabled_sources":enabled,"successful_sources":success,"catalog_rows":len(catalog),"price_rows":len(price),"conflict_rows":len(conflicts),"backfill_ready":bool(len(catalog)>0 and len(conflicts)==0 and success==enabled)}])
    return AcquisitionBuildResult({
      "secret_lair_acquisition_sources":sources,
      "secret_lair_acquisition_catalog":catalog,
      "secret_lair_acquisition_prices":price,
      "secret_lair_acquisition_conflicts":conflicts,
      "secret_lair_acquisition_coverage":coverage,
      "secret_lair_acquisition_run_log":logs,
      "secret_lair_acquisition_summary":summary,
    },exists)
