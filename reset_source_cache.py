from pathlib import Path
import shutil

from config import DATABASE_FILE, SOURCE_CACHE_DIR, HISTORY_DIR, OUTPUT_DIR, ROOT_DIR

def delete_path(path):
    path = Path(path)
    if path.is_file():
        path.unlink()
        print(f"Deleted file: {path}")
    elif path.is_dir():
        shutil.rmtree(path)
        print(f"Deleted folder: {path}")

def main():
    print("Resetting source cache/database so stale case-level prices are removed...")

    delete_path(DATABASE_FILE)
    delete_path(SOURCE_CACHE_DIR / "latest_prices.csv")

    # Keep folders but clear discovered files.
    discovered = ROOT_DIR / "data" / "discovered"
    if discovered.exists():
        for file in discovered.glob("*.csv"):
            file.unlink()
            print(f"Deleted discovered file: {file}")

    print("\nDone. Now run:")
    print("python run.py")

if __name__ == "__main__":
    main()
