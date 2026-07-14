from __future__ import annotations
import csv
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
from .contracts import ACQUISITION_CONTRACTS
from terminal2.warehouse_core import get_warehouse_config

@dataclass(frozen=True)
class AcquisitionValidationResult:
    passed: bool; errors: tuple[str,...]; warnings: tuple[str,...]; datasets_checked: int; catalog_rows: int; conflict_rows: int

def validate_secret_lair_acquisition(project_root: Path|None=None) -> AcquisitionValidationResult:
    cfg=get_warehouse_config(project_root); manifest_path=cfg.manifests_root/"dataset_manifest.csv"; errors=[]; warnings=[]; catalog_rows=0; conflict_rows=0
    if not manifest_path.exists(): return AcquisitionValidationResult(False,(f"Dataset manifest is missing: {manifest_path}",),(),0,0,0)
    with manifest_path.open('r',newline='',encoding='utf-8') as h: manifest={r['dataset_name']:r for r in csv.DictReader(h)}
    frames={}
    for name,contract in ACQUISITION_CONTRACTS.items():
        row=manifest.get(name)
        if row is None: errors.append(f"Required acquisition dataset is missing: {name}"); continue
        path=Path(row['current_path'])
        if not path.exists(): errors.append(f"Acquisition dataset file is missing: {path}"); continue
        frame=pd.read_csv(path); frames[name]=frame
        missing=sorted(set(contract.required_columns)-set(frame.columns))
        if missing: errors.append(f"Dataset '{name}' is missing columns: {missing}")
        if contract.primary_key and not frame.empty:
            keys=frame[list(contract.primary_key)]
            if keys.isna().any(axis=None): errors.append(f"Dataset '{name}' contains null key values.")
            dup=int(keys.duplicated().sum())
            if dup: errors.append(f"Dataset '{name}' has {dup} duplicate key row(s).")
    catalog=frames.get('secret_lair_acquisition_catalog'); conflicts=frames.get('secret_lair_acquisition_conflicts'); sources=frames.get('secret_lair_acquisition_sources')
    if catalog is not None:
        catalog_rows=len(catalog)
        if catalog.empty: warnings.append('No Secret Lair source records were acquired. Configure and enable at least one source.')
    if conflicts is not None:
        conflict_rows=len(conflicts)
        if conflict_rows: warnings.append(f'{conflict_rows} acquisition conflict row(s) require review.')
    if sources is not None and not sources.empty:
        failed=int(sources['status'].eq('failed').sum())
        if failed: errors.append(f'{failed} enabled source connector(s) failed.')
    return AcquisitionValidationResult(not errors,tuple(errors),tuple(warnings),len(ACQUISITION_CONTRACTS),catalog_rows,conflict_rows)
