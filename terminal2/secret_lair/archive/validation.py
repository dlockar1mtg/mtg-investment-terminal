from dataclasses import dataclass
from pathlib import Path
import csv,pandas as pd
from terminal2.warehouse_core import get_warehouse_config
from .contracts import ARCHIVE_CONTRACTS
@dataclass(frozen=True)
class ArchiveValidationResult:passed:bool;errors:tuple[str,...];warnings:tuple[str,...];datasets_checked:int;observations:int;covered_products:int;historical_ready:int

def validate_secret_lair_archive(project_root=None):
 cfg=get_warehouse_config(project_root);mp=cfg.manifests_root/'dataset_manifest.csv';errors=[];warnings=[];frames={}
 if not mp.exists():return ArchiveValidationResult(False,(f'Missing manifest: {mp}',),(),0,0,0,0)
 with mp.open('r',newline='',encoding='utf-8') as h:m={r['dataset_name']:r for r in csv.DictReader(h)}
 for n,c in ARCHIVE_CONTRACTS.items():
  row=m.get(n)
  if not row:errors.append(f'Missing archive dataset: {n}');continue
  p=Path(row['current_path'])
  if not p.exists():errors.append(f'Missing archive file: {p}');continue
  f=pd.read_csv(p);frames[n]=f;missing=set(c.required_columns)-set(f.columns)
  if missing:errors.append(f'{n} missing columns: {sorted(missing)}')
 summary=frames.get('secret_lair_archive_summary',pd.DataFrame());obs=covered=ready=0
 if len(summary)!=1:errors.append('Archive summary must contain exactly one row.')
 else:
  r=summary.iloc[0];obs=int(r['archive_observation_count']);covered=int(r['covered_product_count']);ready=int(r['historical_ready_count'])
  if obs==0:warnings.append('Historical archive is empty. Run the archive builder with --download.')
  if ready==0:warnings.append('No products yet meet the Historical Ready coverage tier.')
 raw=frames.get('secret_lair_archive_raw_prices',pd.DataFrame())
 if not raw.empty and pd.to_numeric(raw['market_price'],errors='coerce').le(0).any():errors.append('Archive contains non-positive prices.')
 return ArchiveValidationResult(not errors,tuple(errors),tuple(warnings),len(ARCHIVE_CONTRACTS),obs,covered,ready)
