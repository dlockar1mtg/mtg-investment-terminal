from dataclasses import dataclass
from terminal2.warehouse_core import DatasetDefinition
@dataclass(frozen=True)
class C:
 name:str;description:str;primary_key:tuple[str,...];required_columns:tuple[str,...];snapshot:bool=True
 def definition(self): return DatasetDefinition(name=self.name,category='secret_lair',module='terminal2.secret_lair.archive',description=self.description,primary_key=self.primary_key,expected_columns=self.required_columns,required=True,snapshot=self.snapshot,version='1')
ARCHIVE_CONTRACTS={
'secret_lair_archive_sources':C('secret_lair_archive_sources','Configured historical archive sources.',('source_name',),('source_name','base_url','start_date','enabled','status')),
'secret_lair_archive_download_log':C('secret_lair_archive_download_log','Snapshot download and extraction audit.',('snapshot_date',),('snapshot_date','status','download_status','extract_status','files_checked','rows_found','message'),False),
'secret_lair_archive_raw_prices':C('secret_lair_archive_raw_prices','Validated raw historical archive prices.',('observation_date','secret_lair_id','source_name'),('observation_date','secret_lair_id','source_name','market_price','low_price','tcgplayer_product_id','tcgcsv_group_id'),False),
'secret_lair_archive_monthly_prices':C('secret_lair_archive_monthly_prices','Canonical monthly Secret Lair prices.',('price_month','secret_lair_id','source_name'),('price_month','secret_lair_id','source_name','market_price','low_price','observation_count','latest_observation_date'),False),
'secret_lair_archive_coverage':C('secret_lair_archive_coverage','Per-product history coverage.',('secret_lair_id',),('secret_lair_id','product_name','observation_count','month_count','first_observation_date','latest_observation_date','history_span_days','coverage_tier')),
'secret_lair_archive_gaps':C('secret_lair_archive_gaps','Missing months inside observed history windows.',('secret_lair_id','missing_month'),('secret_lair_id','product_name','missing_month','gap_type'),False),
'secret_lair_archive_conflicts':C('secret_lair_archive_conflicts','Conflicting prices for identical product dates.',('observation_date','secret_lair_id'),('observation_date','secret_lair_id','source_count','minimum_price','maximum_price','price_spread_pct'),False),
'secret_lair_archive_import_candidates':C('secret_lair_archive_import_candidates','Validated production import candidates.',('observation_date','secret_lair_id','source_name'),('observation_date','secret_lair_id','source_name','market_price','low_price','price_data_quality','import_eligible','import_reason'),False),
'secret_lair_archive_summary':C('secret_lair_archive_summary','Executive archive status.',('snapshot_date',),('snapshot_date','mapped_product_count','archive_observation_count','covered_product_count','historical_ready_count','gap_count','conflict_count','import_candidate_count','apply_ready')),
}
def get_archive_contract(n):
 try:return ARCHIVE_CONTRACTS[n]
 except KeyError as e:raise KeyError(f'Unknown archive contract: {n}') from e
