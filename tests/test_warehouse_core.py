from pathlib import Path
import pytest
from terminal2.warehouse_core import DatasetDefinition,DatasetRegistry,Warehouse,get_warehouse_config
from terminal2.warehouse_core.paths import normalize_dataset_name
from terminal2.warehouse_core.validation import validate_warehouse
def test_names(): assert normalize_dataset_name('Market Health')=='market_health'
def test_bad_name():
    with pytest.raises(ValueError): normalize_dataset_name('123 bad')
def test_duplicate(tmp_path):
    c=get_warehouse_config(tmp_path); r=DatasetRegistry(c); d=DatasetDefinition('market_health','market','test'); r.register(d)
    with pytest.raises(ValueError): r.register(d)
def test_init(tmp_path):
    w=Warehouse(config=get_warehouse_config(tmp_path)); w.initialize(); assert validate_warehouse(w).passed
