# Phase 10.1 MTG Baseline

## Status

Baseline complete.

## Repository

- Branch: phase-10-mtg-production-hardening
- Commit: 459aea7591a7df742d17bb614036235dc9491063
- Python: Python 3.14.6

## Archive Environment

- py7zr installed: True
- py7zr version: 1.1.3
- External 7-Zip dependency found: True

## External 7-Zip Dependency Locations

- terminal2/sources/tcgcsv_archive.py
- backfill_tcgcsv_monthly_history.py

## Repository Counts

- Python files: 357
- Test files: 75
- CSV files: 14
- Markdown files: 128

## Runtime Files

- Database files found: 0
- Archive files found: 0

## Test Collection

- Exit code: 0

## Phase 10.2 Required Work

- Add py7zr to requirements.txt.
- Replace all 7z.exe and external 7-Zip extraction.
- Create one shared Python-native archive extraction service.
- Update both historical archive pipelines to use it.
- Add archive extraction and safety tests.
- Run the full MTG test suite.
