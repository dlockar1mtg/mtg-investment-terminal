import csv
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
from terminal2.secret_lair.discovery.contracts import DISCOVERY_CONTRACTS
from terminal2.warehouse_core import get_warehouse_config
@dataclass(frozen=True)
class DiscoveryValidationResult: passed:bool; errors:tuple[str,...]; warnings:tuple[str,...]; datasets_checked:int; discovered_rows:int; conflict_rows:int
def validate_secret_lair_discovery(project_root=None):
    cfg=get_warehouse_config(project_root); m=cfg.manifests_root/'dataset_manifest.csv'; errors=[]; warnings=[]; discovered=conflicts=0
    if not m.exists():return DiscoveryValidationResult(False,(f'Dataset manifest is missing: {m}',),(),0,0,0)
    with m.open('r',newline='',encoding='utf-8') as h:manifest={r['dataset_name']:r for r in csv.DictReader(h)}
    frames={}
    for name,c in DISCOVERY_CONTRACTS.items():
        row=manifest.get(name)
        if not row:errors.append(f'Required discovery dataset is missing: {name}');continue
        path=Path(row['current_path'])
        if not path.exists():errors.append(f'Discovery dataset file is missing: {path}');continue
        f=pd.read_csv(path);frames[name]=f;missing=sorted(set(c.required_columns)-set(f.columns))
        if missing:errors.append(f"Dataset '{name}' is missing columns: {missing}")
        if c.primary_key and not f.empty:
            keys=f[list(c.primary_key)]
            if keys.isna().any(axis=None):errors.append(f"Dataset '{name}' contains null key values.")
            d=int(keys.duplicated().sum())
            if d:errors.append(f"Dataset '{name}' has {d} duplicate key row(s).")
    cat=frames.get('secret_lair_discovery_catalog'); con=frames.get('secret_lair_discovery_conflicts'); health=frames.get('secret_lair_discovery_source_health')
    if cat is not None:
        discovered=len(cat)
        if cat.empty:warnings.append('No Secret Lair discovery records were found. Configure and enable at least one discovery source.')
    if con is not None:
        conflicts=len(con)
        if conflicts:warnings.append(f'{conflicts} discovery conflict row(s) require review.')
    if health is not None and not health.empty:
        failed=health[health['status'].eq('failed')]
        if len(failed):warnings.append(f'{len(failed)} discovery source(s) failed.')
    return DiscoveryValidationResult(not errors,tuple(errors),tuple(warnings),len(DISCOVERY_CONTRACTS),discovered,conflicts)
