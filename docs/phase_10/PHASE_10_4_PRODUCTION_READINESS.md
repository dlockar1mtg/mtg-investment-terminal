# Phase 10.4 — MTG Production-Readiness Certification

## Status

**PASS**

Phase 10.4 certifies repository-level startup, dependency,
configuration, database, network-source, archive, and report-generation
readiness before the Universal export adapter is constructed.

## Remediation completed

The audit found an obsolete import contract:

`terminal2.exports.export_reports`

The referenced package and `export_all()` function no longer existed,
preventing the canonical orchestrator from importing.

Phase 10.4:

- removed the obsolete import and call from `terminal2_run_all.py`;
- removed the obsolete import and call from
  `terminal2_module2_run_all.py`;
- converted `terminal2_export.py` into a compatibility entry point for
  the dashboard warehouse publisher;
- added production startup and readiness regression tests.

## Certification gates

The readiness runner verifies:

1. Required runtime dependencies are installed.
2. Primary production modules import successfully.
3. Obsolete export-package references are absent.
4. Database migrations run idempotently against an isolated temporary
   SQLite database.
5. Required tables exist and SQLite integrity checks pass.
6. Required output roots exist.
7. Configured storage paths resolve inside the repository.
8. Network-source modules contain explicit timeout controls.
9. Active archive pipelines use Python-native extraction.

## Certification command

Run from the repository root:

    python .\scripts\certify_phase_10_4.py

A blocking failure returns a nonzero exit code.

## Generated evidence

The runner creates:

    data/validation/phase_10/production_readiness/
        phase_10_4_production_readiness.json
        phase_10_4_production_readiness.md

These generated reports are excluded from Git.

## Current certified result

- Overall readiness: PASS
- Production modules imported: 21
- Configuration paths checked: 5
- Network-source modules checked: 7
- Database migration and integrity: PASS
- Python-native archive handling: PASS

## Certification boundaries

This certification does not prove:

- current availability of every external API or archive endpoint;
- validity of every live credential or access policy;
- completeness of every historical data file;
- successful execution of the full orchestrator against production
  data;
- economic accuracy of every investment recommendation.

Universal output-contract and sandbox-import validation are addressed
in Phase 10.5.