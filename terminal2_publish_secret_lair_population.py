from terminal2.secret_lair.population import publish_secret_lair_population
def main():
 r=publish_secret_lair_population();print("\nTerminal 2.9.6 Secret Lair Data Population");print("="*64)
 for label,key in [("Datasets published","datasets"),("Catalog rows","catalog_rows"),("Accepted rows","accepted_rows"),("Review rows","review_rows"),("Proposed registry assets","registry_assets"),("Priced assets","priced_assets"),("Scoring-ready assets","scoring_ready_assets")]:print(f"{label}: {r[key]}")
 print(f"Apply ready: {r['apply_ready']}")
if __name__=='__main__':main()
