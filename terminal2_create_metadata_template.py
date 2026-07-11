from terminal2.metadata.enrichment import create_template
from terminal2.config import METADATA_TEMPLATE_FILE

if __name__ == "__main__":
    data = create_template()
    print(f"Template created: {METADATA_TEMPLATE_FILE}")
    print(f"Rows: {len(data)}")
