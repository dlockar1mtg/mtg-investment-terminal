from dataclasses import dataclass
from pathlib import Path
import csv,pandas as pd
from terminal2.warehouse_core import get_warehouse_config
from .contracts import MASTER_DATABASE_CONTRACTS
@dataclass(frozen=True)
class MasterDatabaseValidationResult:
 passed:bool;errors:tuple[str,...];warnings:tuple[str,...];datasets_checked:int;canonical_products:int;current_prices:int;review_rows:int

def validate_master_secret_lair_database(project_root=None):
 cfg=get_warehouse_config(project_root);mp=cfg.manifests_root/"dataset_manifest.csv";errors=[];warnings=[];frames={}
 if not mp.exists():return MasterDatabaseValidationResult(False,(f"Missing manifest: {mp}",),(),0,0,0,0)
 with mp.open("r",newline="",encoding="utf-8") as h:manifest={r["dataset_name"]:r for r in csv.DictReader(h)}
 for n,c in MASTER_DATABASE_CONTRACTS.items():
  row=manifest.get(n)
  if not row:errors.append(f"Missing master database dataset: {n}");continue
  p=Path(row["current_path"])
  if not p.exists():errors.append(f"Missing dataset file: {p}");continue
  f=pd.read_csv(p);frames[n]=f;missing=set(c.required_columns)-set(f.columns)
  if missing:errors.append(f"{n} missing columns: {sorted(missing)}")
  if c.primary_key and not f.empty and f[list(c.primary_key)].duplicated().any():errors.append(f"{n} has duplicate primary keys")
 products=frames.get("master_secret_lair_products",pd.DataFrame());prices=frames.get("master_secret_lair_prices_current",pd.DataFrame());review=frames.get("master_secret_lair_review_queue",pd.DataFrame())
 if products.empty:warnings.append("No canonical Secret Lair products were found. Run with live internet access and review source connectivity.")
 if not products.empty and prices.empty:warnings.append("Products were found but no current product-level prices were matched.")
 if len(review):warnings.append(f"{len(review)} product record(s) require manual review before registry import.")
 return MasterDatabaseValidationResult(not errors,tuple(errors),tuple(warnings),len(MASTER_DATABASE_CONTRACTS),len(products),len(prices),len(review))
