import argparse
from terminal2.secret_lair.master_database import publish_master_secret_lair_database

def main():
 p=argparse.ArgumentParser();p.add_argument("--refresh",action="store_true");p.add_argument("--max-tcgcsv-groups",type=int);a=p.parse_args();r=publish_master_secret_lair_database(refresh=a.refresh,max_tcgcsv_groups=a.max_tcgcsv_groups)
 print("\nTerminal 2.9.7 Master Secret Lair Database");print("="*64)
 print(f"Datasets published: {r['datasets']}");print(f"Source products: {r['source_products']}");print(f"Canonical products: {r['canonical_products']}");print(f"Current prices: {r['current_prices']}");print(f"Historical observations: {r['history_rows']}");print(f"Review rows: {r['review_rows']}");print(f"Registry-ready products: {r['registry_ready']}");print(f"Local master root: {r['local_root']}")
if __name__=="__main__":main()
