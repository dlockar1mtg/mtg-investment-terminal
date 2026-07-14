from dataclasses import dataclass
from terminal2.warehouse_core import DatasetDefinition
@dataclass(frozen=True)
class DiscoveryContract:
    name:str; description:str; primary_key:tuple[str,...]; required_columns:tuple[str,...]; snapshot:bool=True; version:str='1'
    def definition(self):
        return DatasetDefinition(name=self.name,category='secret_lair',module='terminal2.secret_lair.discovery',description=self.description,primary_key=self.primary_key,expected_columns=self.required_columns,required=True,snapshot=self.snapshot,version=self.version)
DISCOVERY_CONTRACTS={
 'secret_lair_discovery_source_health':DiscoveryContract('secret_lair_discovery_source_health','Discovery connector configuration and health.',('source_name',),('source_name','connector_type','parser_name','enabled','status','records_received','records_normalized'),False),
 'secret_lair_discovery_catalog':DiscoveryContract('secret_lair_discovery_catalog','Normalized records discovered from enabled sources.',('source_name','source_record_id'),('source_name','source_record_id','drop_name','variant_name','finish','discovered_at_utc')),
 'secret_lair_discovery_candidates':DiscoveryContract('secret_lair_discovery_candidates','New and reviewable discovery candidates.',('source_name','source_record_id'),('source_name','source_record_id','candidate_status','candidate_confidence','drop_name','variant_name','finish')),
 'secret_lair_discovery_known':DiscoveryContract('secret_lair_discovery_known','Discovery records already known to the platform.',('source_name','source_record_id'),('source_name','source_record_id','known_match_type','known_secret_lair_id','drop_name')),
 'secret_lair_discovery_conflicts':DiscoveryContract('secret_lair_discovery_conflicts','Duplicate or incomplete discovery records.',('conflict_id',),('conflict_id','source_name','source_record_id','conflict_type','message'),False),
 'secret_lair_discovery_run_log':DiscoveryContract('secret_lair_discovery_run_log','One row per source connector execution.',('run_id','source_name'),('run_id','source_name','started_at_utc','completed_at_utc','status','records_received','records_normalized'),False),
 'secret_lair_discovery_summary':DiscoveryContract('secret_lair_discovery_summary','Executive discovery summary.',('snapshot_date',),('snapshot_date','enabled_sources','successful_sources','discovered_rows','new_candidate_rows','known_rows','conflict_rows')),
}
def get_discovery_contract(name):
    try:return DISCOVERY_CONTRACTS[name]
    except KeyError as exc: raise KeyError(f'Unknown Secret Lair discovery contract: {name}') from exc
