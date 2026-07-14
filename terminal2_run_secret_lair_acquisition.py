from terminal2.secret_lair.acquisition import publish_secret_lair_acquisition

def main():
    r=publish_secret_lair_acquisition()
    print("\nTerminal 2.7.0 Secret Lair Source Acquisition")
    print("="*60)
    print(f"Datasets published: {r['datasets']}")
    print(f"Source configuration found: {r['source_config_exists']}")
    print(f"Enabled sources: {r['enabled_sources']}")
    print(f"Successful sources: {r['successful_sources']}")
    print(f"Catalog rows: {r['catalog_rows']}")
    print(f"Price rows: {r['price_rows']}")
    print(f"Conflict rows: {r['conflict_rows']}")
    print(f"Backfill ready: {r['backfill_ready']}")
if __name__=='__main__': main()
