from pathlib import Path
import shutil
from terminal2.config import ROOT_DIR
from terminal2.secret_lair.discovery.config import DISCOVERY_CONFIG_PATH
def main():
    template=Path(ROOT_DIR)/'data'/'templates'/'secret_lair_discovery_sources_template.csv'; DISCOVERY_CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
    if not DISCOVERY_CONFIG_PATH.exists():shutil.copy2(template,DISCOVERY_CONFIG_PATH)
    print(f'Secret Lair discovery source template ready: {DISCOVERY_CONFIG_PATH}')
if __name__=='__main__':main()
