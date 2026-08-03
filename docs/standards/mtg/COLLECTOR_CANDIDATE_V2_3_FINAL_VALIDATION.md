# Collector Candidate v2.3 Final Validation and Freeze Recommendation

## Purpose

This batch determines whether Collector Candidate Methodology v2.3 is structurally ready to be frozen as the technical Collector forecast candidate.

It does not authorize production forecasts, purchases, reverse-score production use, automatic model updates, the Japanese FINAL FANTASY hybrid formula, or prospective accuracy certification.

## Inputs

- Candidate v2.3 forecasts and summary
- Candidate v2.3 approval record
- Candidate v2.3 builder
- Candidate v2.3 audit

## Outputs

- `collector_candidate_v2_3_artifact_hash_manifest.csv`
- `collector_candidate_v2_3_final_route_validation.csv`
- `collector_candidate_v2_3_exception_register.csv`
- `collector_candidate_v2_3_freeze_recommendation.json`
- `collector_candidate_v2_3_final_validation_summary.json`

## Freeze policy

A technical freeze may be recommended with explicit exclusions when:

- all 51 products are represented;
- 50 calculations are complete;
- the Japanese hybrid remains inactive;
- seven reverse-score routes remain diagnostic-only;
- scenario bounds and confidence ceilings pass;
- restricted authorizations remain closed;
- the candidate artifacts are hashed;
- all unresolved exceptions are registered.

## Required exclusions

- Reverse-score routes are not production eligible.
- Japanese FINAL FANTASY hybrid formula remains inactive.
- Production forecast authorization has not been granted.
- Purchase recommendation authorization has not been granted.
- Prospective forecast accuracy has not been certified.

## Commands

```powershell
python scripts\build_collector_candidate_v2_3_final_validation.py
python scripts\build_collector_candidate_v2_3_final_validation.py --strict
python scripts\audit_collector_candidate_v2_3_final_validation.py
python scripts\audit_collector_candidate_v2_3_final_validation.py --strict
```

## Interpretation

`TECHNICAL_FREEZE_RECOMMENDED_WITH_EXCLUSIONS` means v2.3 may be proposed to the owner as the frozen technical forecast candidate. It does not freeze the candidate automatically and does not open any production or purchase authorization.
