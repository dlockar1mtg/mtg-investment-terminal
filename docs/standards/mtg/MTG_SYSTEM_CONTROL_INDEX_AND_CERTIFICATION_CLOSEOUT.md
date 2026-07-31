# MTG System Control Index and Certification Closeout

## Purpose

The MTG System Control Index is the first document and configuration artifact to review before future MTG implementation, diagnosis, cleanup, or UIP integration work.

It exists to prevent repeated repository-wide discovery and accidental use of legacy, backup, repair, archived, superseded, current-only, or otherwise unauthorized files.

## Required review order

1. `config/mtg/governance/mtg_system_control_index_v1.json`
2. The certified active-file allowlist for the relevant scope
3. The authoritative pipeline map
4. The data-source and lineage map
5. The model and parameter version map
6. The owner approval register
7. The prohibited-path register
8. The applicable operations or backtest runbook
9. The latest certification and change-control history

Repository-wide inspection is a fallback only when the index is missing, incomplete, internally inconsistent, or explicitly under recertification.

## Certification scopes

The index covers four independent closeout scopes:

- Collector Booster
- Pre-Collector
- Secret Lair
- MTG-to-UIP connection

Each scope is independently certified and cleaned before the final end-to-end closeout.

## Lane closeout checklist

A scope cannot reach `CERTIFIED_POST_CLEANUP` until all items below are complete.

1. Functional and semantic certification passed.
2. Owner acceptance recorded.
3. Certified code, configuration, model, parameter, and data-contract versions frozen.
4. Active runtime and backtest dependencies enumerated.
5. Certified active-file allowlist created.
6. Authoritative pipeline map created.
7. Data-source and lineage map created.
8. Model and parameter version map created.
9. Owner approval register reconciled.
10. Prohibited-path register created.
11. Every related file assigned a disposition class.
12. Archive manifest reviewed.
13. Delete-candidate manifest reviewed by the owner.
14. Approved archive moves completed.
15. Approved deletions completed.
16. Production discovery restricted to allowlisted inputs.
17. Backup, repair, archive, and superseded paths verified as unreachable by production.
18. Daily operations runbook completed.
19. Backtest and recalibration runbook completed.
20. Post-cleanup full certification rerun and passed.
21. Control index updated with certified paths, versions, commit, and reports.

## Disposition rule

Archive is the default. Deletion requires explicit owner approval and evidence that the file is a verified duplicate, transient generated artifact, empty output, or reproducible cache with no unique historical, evidentiary, operational, or lineage value.

## Collector development status

The Collector scope is currently `IN_PROGRESS`. Cleanup execution is not authorized while historical-source adjudication, snapshot construction, candidate forecasting, backtesting, exact numeric approval, and production certification remain incomplete.

## Final UIP closeout

After all three MTG lanes are independently certified and cleaned, the UIP connection closeout must reconcile the three lane allowlists, validate the interface contract, remove or archive conflicting delivery pathways, run end-to-end no-loss semantic certification, and update the permanent System Control Index.
