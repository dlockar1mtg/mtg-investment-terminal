# Collector Methodology Adjustment Trace and Final Ballot

## Purpose

This inactive control batch traces the comparable-route difference between the reconciled baseline annual rate and the peer-only weighted rate. It compares that difference directly with the existing `fundamental_adjustment_annual_rate` field and preserves any residual as unexplained rather than assigning an unsupported label.

It also produces the final six-decision owner ballot. No decision is inferred from prior recommendations, and no methodology, forecast, purchase recommendation, or automatic update is authorized.

## Inputs

- Collector methodology decision capture outputs
- Collector reconciled candidate forecasts
- Collector methodology owner decision package

## Outputs

- `collector_comparable_adjustment_trace.csv`
- `collector_comparable_adjustment_trace_groups.csv`
- `collector_methodology_final_owner_ballot.csv`
- `collector_methodology_final_inactive_specification.json`
- `collector_methodology_adjustment_trace_and_final_ballot_summary.json`

## Required commands

```powershell
python scripts\build_collector_methodology_adjustment_trace_and_final_ballot.py
python scripts\build_collector_methodology_adjustment_trace_and_final_ballot.py --strict
python scripts\audit_collector_methodology_adjustment_trace_and_final_ballot.py
python scripts\audit_collector_methodology_adjustment_trace_and_final_ballot.py --strict
```

## Interpretation boundary

A successful trace proves only that the numerical baseline-minus-peer difference matches an existing forecast field within tolerance. It does not prove that the field's economic construction is correct or approved. The owner must still make all six explicit methodology decisions before an approved candidate can be built.
