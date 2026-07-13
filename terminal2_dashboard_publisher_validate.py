from pathlib import Path
import tempfile
import pandas as pd
from terminal2.warehouse_core import DashboardPublisher, DatasetDefinition, Warehouse, get_warehouse_config

def main():
    with tempfile.TemporaryDirectory(prefix='mtg_publisher_validation_') as temp:
        warehouse=Warehouse(config=get_warehouse_config(Path(temp))); publisher=DashboardPublisher(warehouse)
        df=pd.DataFrame({'investment_product_id':['p1','p2','p3'],'box_name':['Alpha','Beta','Gamma'],'investment_score':[91.2,83.5,77.1]})
        definition=DatasetDefinition(name='publisher_validation',category='admin',module='terminal2.warehouse_core',description='Publisher self-validation.',primary_key=('investment_product_id',),expected_columns=('investment_product_id','box_name','investment_score'),required=True,snapshot=True)
        result=publisher.publish(df,definition)
        required=[Path(result.current_path),Path(result.snapshot_path),warehouse.config.manifests_root/'dataset_manifest.csv',warehouse.config.manifests_root/'data_dictionary.csv',warehouse.config.logs_root/'publication_log.csv']
        missing=[str(p) for p in required if not p.exists()]
        if missing: raise SystemExit('FAILED: Missing outputs: '+', '.join(missing))
        if len(pd.read_csv(result.current_path))!=3: raise SystemExit('FAILED: Published row count is incorrect.')
        print('Terminal 2.5.1b Dashboard Publisher validation')
        print('='*56); print(f'Dataset: {result.dataset_name}'); print(f'Rows: {result.row_count}'); print(f'Columns: {result.column_count}'); print('PASS: Dashboard Publisher is functioning correctly.')
if __name__=='__main__': main()
