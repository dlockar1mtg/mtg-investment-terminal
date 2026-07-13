from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
try:
    from terminal2.config import ROOT_DIR
except Exception:
    ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CATEGORIES=("executive","rankings","market","products","lifecycle","seasonality","research","alerts","metadata","intelligence","portfolio","semantic","admin")
@dataclass(frozen=True)
class WarehouseConfig:
    project_root: Path
    warehouse_root: Path
    current_root: Path
    history_root: Path
    reports_root: Path
    manifests_root: Path
    logs_root: Path
    categories: tuple[str,...]=field(default_factory=lambda:DEFAULT_CATEGORIES)
    version: str="2.5.1a"
    schema_version: str="1"
    refresh_id_format: str="%Y%m%dT%H%M%SZ"
    max_dataset_name_length: int=120
    csv_encoding: str="utf-8"
    snapshot_date_format: str="%Y-%m-%d"
    def category_path(self,category:str)->Path:
        c=category.strip().lower()
        if c not in self.categories: raise ValueError(f"Invalid warehouse category: {category}")
        return self.current_root/c
    def all_required_paths(self):
        yield from [self.warehouse_root,self.current_root,self.history_root,self.reports_root,self.manifests_root,self.logs_root]
        for c in self.categories: yield self.current_root/c
def get_warehouse_config(project_root:Path|None=None)->WarehouseConfig:
    root=Path(project_root or ROOT_DIR).resolve(); w=root/'data'/'warehouse'
    return WarehouseConfig(root,w,w/'current',w/'history',w/'reports',w/'manifests',w/'logs')
