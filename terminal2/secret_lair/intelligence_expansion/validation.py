from dataclasses import dataclass
from pathlib import Path
import csv,pandas as pd
from terminal2.warehouse_core import get_warehouse_config
from .contracts import EXPANSION_CONTRACTS
@dataclass(frozen=True)
class ExpansionValidationResult:passed:bool;errors:tuple[str,...];warnings:tuple[str,...];datasets_checked:int;secret_lair_assets:int;unified_products:int
def validate_secret_lair_intelligence_expansion(project_root=None):
 cfg=get_warehouse_config(project_root);mp=cfg.manifests_root/'dataset_manifest.csv';errors=[];warnings=[];frames={}
 if not mp.exists():return ExpansionValidationResult(False,(f'Missing manifest: {mp}',),(),0,0,0)
 with mp.open('r',newline='',encoding='utf-8') as h:manifest={r['dataset_name']:r for r in csv.DictReader(h)}
 for n,c in EXPANSION_CONTRACTS.items():
  row=manifest.get(n)
  if row is None:errors.append(f'Missing expansion dataset: {n}');continue
  path=Path(row['current_path'])
  if not path.exists():errors.append(f'Missing dataset file: {path}');continue
  f=pd.read_csv(path);frames[n]=f;missing=set(c.required_columns)-set(f.columns)
  if missing:errors.append(f'{n} missing columns: {sorted(missing)}')
  if c.primary_key and not f.empty and f[list(c.primary_key)].duplicated().any():errors.append(f'{n} has duplicate primary keys')
 assets=len(frames.get('secret_lair_investment_universe',pd.DataFrame()));unified=len(frames.get('unified_investment_products',pd.DataFrame()))
 if assets==0:warnings.append('Secret Lair intelligence is empty. Populate the registry and price observations before evaluating this asset class.')
 return ExpansionValidationResult(not errors,tuple(errors),tuple(warnings),len(EXPANSION_CONTRACTS),assets,unified)
