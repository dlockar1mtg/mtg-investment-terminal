from __future__ import annotations
import csv, hashlib, os, shutil, tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import pandas as pd
from .dataset_registry import DatasetDefinition
from .paths import current_dataset_path, history_dataset_path
from .warehouse import Warehouse

@dataclass(frozen=True)
class PublishResult:
    dataset_name:str; category:str; current_path:str; snapshot_path:str
    refresh_id:str; published_at_utc:str; row_count:int; column_count:int
    file_size_bytes:int; sha256:str; status:str='success'; warnings:tuple[str,...]=()
    def to_record(self):
        d=asdict(self); d['warnings']='|'.join(self.warnings); return d

class DashboardPublisher:
    def __init__(self, warehouse:Warehouse|None=None):
        self.warehouse=warehouse or Warehouse(); self.config=self.warehouse.config

    def publish(self,dataframe:pd.DataFrame,definition:DatasetDefinition,*,refresh_id:str|None=None,create_snapshot:bool|None=None,allow_empty:bool=True)->PublishResult:
        if not isinstance(dataframe,pd.DataFrame): raise TypeError('dataframe must be a pandas DataFrame.')
        self.warehouse.initialize()
        if self.warehouse.registry.contains(definition.name):
            registered=self.warehouse.registry.get(definition.name)
        else:
            registered=self.warehouse.register(definition)
        warnings=self._validate(dataframe,registered,allow_empty)
        active=self.warehouse.refresh.active_run
        rid=refresh_id or (active.refresh_id if active and active.status=='running' else '') or datetime.now(timezone.utc).strftime(self.config.refresh_id_format)
        now=datetime.now(timezone.utc)
        current=current_dataset_path(self.config,registered.category,registered.name)
        self._atomic_write(dataframe,current)
        snap=''
        enabled=registered.snapshot if create_snapshot is None else bool(create_snapshot)
        if enabled:
            target=history_dataset_path(self.config,now.strftime(self.config.snapshot_date_format),rid,registered.category,registered.name)
            target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(current,target); snap=str(target)
        result=PublishResult(registered.name,registered.category,str(current),snap,rid,now.isoformat(),len(dataframe),len(dataframe.columns),current.stat().st_size,self._sha256(current),warnings=tuple(warnings))
        self._append_log(result); self._manifest(result,registered); self._dictionary(dataframe,registered,result)
        return result

    def publish_many(self,datasets:Iterable[tuple[pd.DataFrame,DatasetDefinition]],*,message='Dashboard publication run'):
        run=self.warehouse.refresh.start(message); results=[]
        try:
            for df,definition in datasets: results.append(self.publish(df,definition,refresh_id=run.refresh_id))
            self.warehouse.refresh.finish(status='success',datasets_published=len(results),warnings=sum(len(r.warnings) for r in results)); return results
        except Exception as exc:
            self.warehouse.refresh.fail(exc); raise

    def _validate(self,df,definition,allow_empty):
        warnings=[]
        if df.empty:
            if not allow_empty: raise ValueError(f"Dataset '{definition.name}' contains zero rows.")
            warnings.append('Dataset contains zero rows.')
        dup=df.columns[df.columns.duplicated()].tolist()
        if dup: raise ValueError(f"Dataset '{definition.name}' has duplicate columns: {dup}")
        missing=sorted(set(definition.expected_columns)-set(df.columns))
        if missing: raise ValueError(f"Dataset '{definition.name}' is missing expected columns: {missing}")
        if definition.primary_key:
            missing_keys=[k for k in definition.primary_key if k not in df.columns]
            if missing_keys: raise ValueError(f"Dataset '{definition.name}' is missing primary-key columns: {missing_keys}")
            if not df.empty:
                keys=df[list(definition.primary_key)]
                if keys.isna().any(axis=None): raise ValueError(f"Dataset '{definition.name}' contains null primary-key values.")
                count=int(keys.duplicated().sum())
                if count: raise ValueError(f"Dataset '{definition.name}' contains {count} duplicate primary-key row(s).")
        return warnings

    def _atomic_write(self,df,destination:Path):
        destination.parent.mkdir(parents=True,exist_ok=True); temp=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',newline='',encoding=self.config.csv_encoding,suffix='.csv.tmp',prefix=f'.{destination.stem}_',dir=destination.parent,delete=False) as h:
                temp=Path(h.name); df.to_csv(h,index=False); h.flush(); os.fsync(h.fileno())
            os.replace(temp,destination)
        except Exception:
            if temp and temp.exists(): temp.unlink(missing_ok=True)
            raise

    def _append_log(self,result):
        p=self.config.logs_root/'publication_log.csv'; p.parent.mkdir(parents=True,exist_ok=True); exists=p.exists(); rec=result.to_record()
        with p.open('a',newline='',encoding='utf-8') as h:
            w=csv.DictWriter(h,fieldnames=rec.keys());
            if not exists: w.writeheader()
            w.writerow(rec)

    def _manifest(self,result,definition):
        p=self.config.manifests_root/'dataset_manifest.csv'; records={}
        if p.exists():
            with p.open('r',newline='',encoding='utf-8') as h:
                for row in csv.DictReader(h): records[row['dataset_name']]=row
        rec={'dataset_name':result.dataset_name,'category':result.category,'module':definition.module,'description':definition.description,'primary_key':'|'.join(definition.primary_key),'dependencies':'|'.join(definition.dependencies),'required':definition.required,'snapshot':definition.snapshot,'dataset_version':definition.version,'terminal_version':self.config.version,'schema_version':self.config.schema_version,'refresh_id':result.refresh_id,'published_at_utc':result.published_at_utc,'row_count':result.row_count,'column_count':result.column_count,'file_size_bytes':result.file_size_bytes,'sha256':result.sha256,'current_path':result.current_path,'snapshot_path':result.snapshot_path,'status':result.status,'warnings':'|'.join(result.warnings)}
        records[result.dataset_name]={k:str(v) for k,v in rec.items()}; p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('w',newline='',encoding='utf-8') as h:
            w=csv.DictWriter(h,fieldnames=rec.keys()); w.writeheader(); [w.writerow(records[n]) for n in sorted(records)]

    def _dictionary(self,df,definition,result):
        p=self.config.manifests_root/'data_dictionary.csv'; existing=[]
        if p.exists():
            with p.open('r',newline='',encoding='utf-8') as h: existing=[r for r in csv.DictReader(h) if r.get('dataset_name')!=definition.name]
        rows=[]; keys=set(definition.primary_key); expected=set(definition.expected_columns)
        for i,col in enumerate(df.columns,1):
            s=df[col]; rows.append({'dataset_name':definition.name,'category':definition.category,'column_ordinal':i,'column_name':str(col),'pandas_dtype':str(s.dtype),'nullable':bool(s.isna().any()),'primary_key':col in keys,'expected_column':col in expected,'non_null_count':int(s.notna().sum()),'unique_count':int(s.nunique(dropna=True)),'refresh_id':result.refresh_id,'published_at_utc':result.published_at_utc})
        fields=['dataset_name','category','column_ordinal','column_name','pandas_dtype','nullable','primary_key','expected_column','non_null_count','unique_count','refresh_id','published_at_utc']
        p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('w',newline='',encoding='utf-8') as h:
            w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(existing+rows)

    @staticmethod
    def _sha256(path):
        d=hashlib.sha256()
        with path.open('rb') as h:
            for block in iter(lambda:h.read(1024*1024),b''): d.update(block)
        return d.hexdigest()

def publish_dataset(dataframe:pd.DataFrame,*,name:str,category:str,module:str,description:str='',primary_key:tuple[str,...]=(),dependencies:tuple[str,...]=(),expected_columns:tuple[str,...]=(),required:bool=False,snapshot:bool=True,version:str='1',allow_empty:bool=True,warehouse:Warehouse|None=None)->PublishResult:
    definition=DatasetDefinition(name=name,category=category,module=module,description=description,primary_key=primary_key,dependencies=dependencies,expected_columns=expected_columns,required=required,snapshot=snapshot,version=version)
    return DashboardPublisher(warehouse).publish(dataframe,definition,allow_empty=allow_empty)
