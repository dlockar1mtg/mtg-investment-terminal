from terminal2.db.schema import init_db
from terminal2.db.module1_migration import migrate_module1
from terminal2.config import DB_FILE


def main():
    init_db()
    migrate_module1()
    print(f"Initialized Module 1 database: {DB_FILE}")


if __name__ == "__main__":
    main()
