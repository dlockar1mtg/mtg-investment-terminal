# v6 Changelog

## Added
- Runtime TCGCSV Magic category auto-detection.
- `debug_source_layer.py`.
- Request logging to `data/logs/source_requests.csv`.
- Source helper logs all URLs/status codes/messages.
- Discovery no longer binds category ID as a frozen default argument.

## Changed
- `TCGCSV_MAGIC_CATEGORY_ID` now defaults to `None`.
- Discovery calls `/tcgplayer/categories` first and selects Magic automatically.
- TCGCSV requests include a custom User-Agent and Accept header.
- Added configurable request delay.

## Why
v5.1 could still call `/tcgplayer/1/groups` after local edits because the category handling was too brittle. v6 makes the source layer observable and self-checking.
