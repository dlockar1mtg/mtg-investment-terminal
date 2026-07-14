import argparse
from terminal2.secret_lair.master_database.engine import build_master_secret_lair_database
from terminal2.secret_lair.master_database.registry_export import export_master_database_import_files

def main():
 p=argparse.ArgumentParser();p.add_argument("--minimum-confidence",type=float,default=75);a=p.parse_args();result=build_master_secret_lair_database(refresh=False);out=export_master_database_import_files(result.datasets,minimum_confidence=a.minimum_confidence)
 print("\nMaster Secret Lair Import Files");print("="*64);print(f"Proposed registry rows: {out['registry_rows']}");print(f"Registry file: {out['registry_path']}");print(f"Proposed price rows: {out['price_rows']}");print(f"Price file: {out['prices_path']}");print("Review these files before using the existing guarded registry and price import commands.")
if __name__=="__main__":main()
