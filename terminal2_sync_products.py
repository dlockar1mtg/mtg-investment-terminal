from terminal2.db.loaders import sync_product_master, load_products_df

def main():
    count = sync_product_master()
    print(f"Synced approved products into SQLite: {count}")
    print(load_products_df()[["investment_product_id","box_name","tcgplayer_product_id"]].head(20).to_string(index=False))

if __name__ == "__main__":
    main()
