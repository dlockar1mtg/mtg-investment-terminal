from __future__ import annotations
from dataclasses import dataclass,field,asdict
from .paths import normalize_dataset_name
@dataclass(frozen=True)
class DatasetDefinition:
    name:str; category:str; module:str; description:str=""
    primary_key:tuple[str,...]=field(default_factory=tuple)
    foreign_keys:tuple[str,...]=field(default_factory=tuple)
    dependencies:tuple[str,...]=field(default_factory=tuple)
    expected_columns:tuple[str,...]=field(default_factory=tuple)
    required:bool=False; snapshot:bool=True; version:str="1"
    def normalized(self,config):
        config.category_path(self.category)
        return DatasetDefinition(normalize_dataset_name(self.name,config.max_dataset_name_length),self.category.strip().lower(),self.module.strip() or "unknown",self.description.strip(),tuple(self.primary_key),tuple(self.foreign_keys),tuple(normalize_dataset_name(x) for x in self.dependencies),tuple(self.expected_columns),bool(self.required),bool(self.snapshot),str(self.version))
    def to_record(self):
        d=asdict(self)
        for k in ('primary_key','foreign_keys','dependencies','expected_columns'): d[k]='|'.join(d[k])
        return d
class DatasetRegistry:
    def __init__(self,config): self.config=config; self._datasets={}
    def register(self,definition):
        d=definition.normalized(self.config)
        if d.name in self._datasets: raise ValueError(f"Dataset already registered: {d.name}")
        self._datasets[d.name]=d; return d
    def register_many(self,definitions):
        for d in definitions: self.register(d)
    def all(self): return tuple(sorted(self._datasets.values(),key=lambda x:x.name))
    def validate_dependencies(self):
        known=set(self._datasets); return [f"{d.name} depends on unregistered dataset {x}" for d in self.all() for x in d.dependencies if x not in known]
