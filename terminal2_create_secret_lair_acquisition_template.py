from pathlib import Path
import shutil
from terminal2.config import ROOT_DIR
from terminal2.secret_lair.acquisition.config import SOURCE_CONFIG_PATH

def main():
    source=Path(ROOT_DIR)/"data"/"templates"/"secret_lair_acquisition_sources_template.csv"
    SOURCE_CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
    if not SOURCE_CONFIG_PATH.exists(): shutil.copy2(source,SOURCE_CONFIG_PATH)
    print(f"Secret Lair acquisition source template ready: {SOURCE_CONFIG_PATH}")
if __name__=='__main__': main()
