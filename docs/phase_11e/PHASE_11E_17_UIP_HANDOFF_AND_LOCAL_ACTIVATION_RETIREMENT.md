# Phase 11E.17 — UIP Handoff and Local Activation Retirement

Phase 11E.17 supersedes the dashboard-ownership portion of Phase 11E.16.

The MTG repository does not own the unified dashboard, automated refresh
schedule, universal import state, or cross-asset semantic layer. Those
responsibilities belong to the Universal Investment Platform.

## MTG repository endpoint

The MTG repository ends each production cycle by:

1. rebuilding governed MTG evidence and intelligence;
2. publishing a versioned Phase 11E.15 package; and
3. writing `data/operations/mtg_uip_handoff/latest_mtg_uip_handoff.json`.

## Manual production cycle

```powershell
python .\scripts\run_phase_11e_17_manual_uip_handoff.py
```

This command is intentionally manual. It produces a validated package and UIP
handoff but does not import into the UIP, schedule future runs, or refresh a
dashboard.

## UIP responsibilities

The Universal Investment Platform owns:

- manual or scheduled invocation of the MTG production cycle;
- package validation and import;
- last-known-good imported state;
- cross-asset intelligence;
- semantic-layer publication;
- dashboard publication and refresh;
- monitoring, scheduling, and alerting.

## Retired local activation

Phase 11E.17 removes the Phase 11E.16 activation hook from
`terminal2_run_all.py` and retires the local governed-terminal activation
scripts and tests. Phase 11E.16 remains in Git history as a technically valid
but architecturally superseded implementation.
