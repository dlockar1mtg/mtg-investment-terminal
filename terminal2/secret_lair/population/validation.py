from dataclasses import dataclass
from pathlib import Path
import csv,pandas as pd
from terminal2.warehouse_core import get_warehouse_config
from .contracts import POPULATION_CONTRACTS
@dataclass(frozen=True)
class PopulationValidationResult:passed:bool;errors:tuple[str,...];warnings:tuple[str,...];datasets_checked:int;catalog_rows:int;registry_assets:int;scoring_ready_assets:int
def validate_secret_lair_population(project_root=None):
 cfg=get_warehouse_config(project_root);mp=cfg.manifests_root/"dataset_manifest.csv";errors=[];warnings=[];frames={}
 if not mp.exists():return PopulationValidationResult(False,(f"Missing manifest: {mp}",),(),0,0,0,0)
 with mp.open('r',newline='',encoding='utf-8') as h:manifest={r['dataset_name']:r for r in csv.DictReader(h)}
 for n,c in POPULATION_CONTRACTS.items():
  row=manifest.get(n)
  if not row:errors.append(f"Missing population dataset: {n}");continue
  path=Path(row['current_path'])
  if not path.exists():errors.append(f"Missing population file: {path}");continue
  f=pd.read_csv(path);frames[n]=f;missing=set(c.required_columns)-set(f.columns)
  if missing:errors.append(f"{n} missing columns: {sorted(missing)}")
  if c.primary_key and not f.empty and f[list(c.primary_key)].duplicated().any():errors.append(f"{n} has duplicate primary keys")
 s=frames.get('secret_lair_population_summary',pd.DataFrame());catalog=registry=ready=0
 if len(s)==1:catalog=int(s.iloc[0]['catalog_rows']);registry=int(s.iloc[0]['registry_assets']);ready=int(s.iloc[0]['scoring_ready_assets'])
 if catalog==0:warnings.append('No Secret Lair population candidates are available. Configure acquisition or curated source files first.')
 elif not bool(s.iloc[0]['apply_ready']):warnings.append('Population is not apply-ready. Resolve review, duplicate, and conflict rows before registry application.')
 if registry and ready==0:warnings.append('Registry candidates exist, but no Secret Lair assets are ready for scoring.')
 return PopulationValidationResult(not errors,tuple(errors),tuple(warnings),len(POPULATION_CONTRACTS),catalog,registry,ready)
