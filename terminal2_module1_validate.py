import sqlite3
import pandas as pd
from terminal2.config import DB_FILE
from terminal2.db.module1_migration import migrate_module1


def main():
    migrate_module1()
    connection = sqlite3.connect(DB_FILE)
    try:
        for table in ["products", "product_metadata", "price_observations", "product_features"]:
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {count}")
        print("\nProducts by type:")
        print(pd.read_sql_query("SELECT product_type, COUNT(*) products FROM products GROUP BY product_type ORDER BY product_type", connection).to_string(index=False))
    finally:
        connection.close()


if __name__ == "__main__": main()
