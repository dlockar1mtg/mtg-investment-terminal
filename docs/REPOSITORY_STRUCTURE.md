# Repository Structure

## Tracked in Git

```text
collectors/
models/
terminal2/
tests/
utils/
scripts/
docs/
dashboard/                source code only
data/product_master/      stable approved product definitions
data/reference/           manually curated reference data
data/templates/           safe templates and schemas
*.py
*.md
requirements.txt
.gitignore
.env.example
config.example.py
```

## Local and generated

```text
data/raw/
data/input/
data/investment/
data/market_inputs/
data/market_intelligence/
data/monte_carlo/
data/source_cache/
data/discovered/
data/dashboard/
data/analytics/
data/warehouse/
data/terminal2/archive_cache/
data/terminal2/extracted_archives/
data/terminal2/exports/
outputs/
workspace/
```

## Design direction

Terminal 2.5 will gradually move runtime artifacts toward:

```text
workspace/
├── raw/
├── cache/
├── history/
├── analytics/
├── market/
├── monte_carlo/
└── temp/
```

Dashboard-ready datasets will ultimately be published through a centralized warehouse. Existing operational paths remain unchanged in 2.5.1a to avoid breaking the current pipeline.
