# Secret Lair Discovery Configuration Guide

The local file is `data/terminal2/secret_lair_discovery_sources.csv`.

Connector types: `http`, `http_json`, `http_jsonl`, `http_html`, `local`, `local_json`, `local_jsonl`, `local_html`.

Parser names: `official_html`, `normalized_json`, `scryfall_cards`, `mtgjson_sets`.

For normalized JSON, `query_json` can include `records_key` and a canonical-to-source `mapping` object.
