import argparse
from terminal2.secret_lair.discovery import discover_secret_lairs,stage_discovery_to_acquisition
from terminal2.secret_lair.discovery.exports import publish_discovery_datasets
def main():
    p=argparse.ArgumentParser();p.add_argument('--stage-acquisition',action='store_true');args=p.parse_args();r=discover_secret_lairs();publish_discovery_datasets(r.datasets);s=r.datasets['secret_lair_discovery_summary'].iloc[0]
    print('\nTerminal 2.7.1 Automated Secret Lair Discovery');print('='*62);print(f'Config file found: {r.config_exists}');print(f"Enabled sources: {int(s['enabled_sources'])}");print(f"Successful sources: {int(s['successful_sources'])}");print(f"Discovered rows: {int(s['discovered_rows'])}");print(f"New candidates: {int(s['new_candidate_rows'])}");print(f"Review candidates: {int(s['review_candidate_rows'])}");print(f"Known rows: {int(s['known_rows'])}");print(f"Conflict rows: {int(s['conflict_rows'])}");print(f"Acquisition stage ready: {bool(s['acquisition_stage_ready'])}")
    if args.stage_acquisition:
        x=stage_discovery_to_acquisition(r);print(f'Staged rows: {x.staged_rows}');print(f'Stage file: {x.output_path}')
    else:print('Mode: DISCOVERY ONLY')
if __name__=='__main__':main()
