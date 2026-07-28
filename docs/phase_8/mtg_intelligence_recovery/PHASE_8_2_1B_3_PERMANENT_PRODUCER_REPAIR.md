# Phase 8.2.1B.3 — Permanent Forecast Producer Repair

This package permanently removes tier multipliers from collector-box horizon fields.

The collector producer now emits:

- observed current market value;
- native Monte Carlo low/base/high when available;
- `OBSERVED_VALUE_ONLY` when a current price exists without a native model;
- no one-, three-, or five-year values unless a future producer explicitly marks `horizon_model_certified=YES`.

The unified intelligence and hosted UIP delivery builders are patched to preserve native ranges and reject uncertified horizon fields.
