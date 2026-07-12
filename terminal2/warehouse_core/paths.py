from __future__ import annotations
import re
from pathlib import Path
from .config import WarehouseConfig
PATTERN=re.compile(r"^[a-z][a-z0-9_]*$")
def normalize_dataset_name(name:str,max_length:int=120)->str:
    n=re.sub(r"_+","_",name.strip().lower().replace("-","_").replace(" ","_"))
    if not n or len(n)>max_length or not PATTERN.fullmatch(n): raise ValueError(f"Invalid dataset name: {name}")
    return n
def current_dataset_path(config:WarehouseConfig,category:str,dataset_name:str)->Path:
    return config.category_path(category)/f"{normalize_dataset_name(dataset_name)}.csv"
def history_dataset_path(config:WarehouseConfig,snapshot_date:str,refresh_id:str,category:str,dataset_name:str)->Path:
    return config.history_root/snapshot_date/refresh_id/category/f"{normalize_dataset_name(dataset_name)}.csv"
