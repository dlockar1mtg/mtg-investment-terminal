# Phase 11E.16 — Terminal Activation and Governed Dashboard Cutover

This milestone activates the Phase 11E.15 production package as the canonical
terminal-facing governed dataset.

## Active terminal root

`data/warehouse/current/governed_terminal/`

## Controls

- Validates manifest status, interface name, and interface version.
- Validates SHA-256 checksums for every required artifact.
- Requires exactly 1,141 universal interface and provenance rows.
- Rejects any package that treats current asking references as sold history.
- Rejects any package that makes current asking references model eligible.
- Preserves a last-known-good package for safe fallback.
- Writes terminal activation health status.
- Integrates activation into `terminal2_run_all.py`.

## Complete command

```powershell
python .\scripts\run_phase_11e_16_terminal_cutover.py
```
