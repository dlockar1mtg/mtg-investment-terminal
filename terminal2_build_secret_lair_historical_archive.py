import argparse
from terminal2.secret_lair.archive.engine import build_secret_lair_archive,apply_archive_to_production
from terminal2.secret_lair.archive.exports import publish_archive_datasets
def main():
 p=argparse.ArgumentParser();p.add_argument('--start');p.add_argument('--end');p.add_argument('--download',action='store_true');p.add_argument('--force',action='store_true');p.add_argument('--apply',action='store_true');a=p.parse_args()
 r=build_secret_lair_archive(start_date=a.start,end_date=a.end,download=a.download,force=a.force);publish_archive_datasets(r.datasets);s=r.datasets['secret_lair_archive_summary'].iloc[0]
 print('\nTerminal 2.10.0 Secret Lair Historical Market Archive');print('='*72)
 for label,key in [('Mapped products','mapped_product_count'),('Archive observations','archive_observation_count'),('Covered products','covered_product_count'),('Historical ready','historical_ready_count'),('Gaps','gap_count'),('Conflicts','conflict_count'),('Import candidates','import_candidate_count'),('Apply ready','apply_ready')]:print(f'{label}: {s[key]}')
 if a.apply:
  added,total,removed=apply_archive_to_production(r);print(f'Applied archive rows: {added}');print(f'Removed orphan production rows: {removed}');print(f'Production price rows: {total}')
 else:print('PREVIEW ONLY: use --apply after reviewing archive outputs.')
if __name__=='__main__':main()
