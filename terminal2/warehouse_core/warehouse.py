from __future__ import annotations
import csv,json
from datetime import datetime,timezone
from .config import get_warehouse_config
from .dataset_registry import DatasetRegistry
from .refresh import RefreshManager
from .version import VersionManager
class Warehouse:
    def __init__(self,config=None,registry=None):
        self.config=config or get_warehouse_config(); self.registry=registry or DatasetRegistry(self.config); self.refresh=RefreshManager(self.config); self.versions=VersionManager(self.config)
    def initialize(self):
        created=[]
        for p in self.config.all_required_paths():
            if not p.exists(): p.mkdir(parents=True,exist_ok=True); created.append(str(p.relative_to(self.config.project_root)))
        self._write_registry(); self._write_status('initialized'); self.versions.append('Warehouse core initialized')
        return {'warehouse_root':str(self.config.warehouse_root),'paths_created':created,'categories':list(self.config.categories),'version':self.config.version,'schema_version':self.config.schema_version}
    def register_many(self,defs): self.registry.register_many(defs); self._write_registry()
    def validate(self):
        errs=[]
        for p in self.config.all_required_paths():
            if not p.exists() or not p.is_dir(): errs.append(f'Missing or invalid warehouse path: {p}')
        errs.extend(self.registry.validate_dependencies()); return errs
    def _write_registry(self):
        p=self.config.manifests_root/'dataset_registry.csv'; p.parent.mkdir(parents=True,exist_ok=True); f=['name','category','module','description','primary_key','foreign_keys','dependencies','expected_columns','required','snapshot','version']
        with p.open('w',newline='',encoding='utf-8') as h:
            w=csv.DictWriter(h,fieldnames=f); w.writeheader(); w.writerows([d.to_record() for d in self.registry.all()])
    def _write_status(self,status):
        p=self.config.manifests_root/'warehouse_status.json'; p.write_text(json.dumps({'status':status,'terminal_version':self.config.version,'schema_version':self.config.schema_version,'warehouse_root':str(self.config.warehouse_root),'categories':list(self.config.categories),'registered_datasets':len(self.registry.all()),'updated_at_utc':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf-8')
