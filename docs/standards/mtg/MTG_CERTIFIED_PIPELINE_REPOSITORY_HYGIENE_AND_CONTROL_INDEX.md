# MTG Certified Pipeline Repository Hygiene and Permanent Control Index

## Purpose

After Collector Booster, Pre-Collector Booster, Secret Lair, and the MTG-to-UIP interface are each certified, the repository must be reduced to an explicitly controlled active surface. The objective is to prevent a future script, developer, or assistant from accidentally selecting a legacy, backup, repair, current-only, superseded, or conflicting file.

## Certification is not complete until cleanup is complete

A lane is not finally certified merely because forecasts and tests pass. Final certification also requires:

1. A frozen certified version.
2. An active-file allowlist.
3. A complete dependency and lineage scan.
4. Disposition of all related files.
5. An archive manifest and any approved deletion manifest.
6. A prohibited-path register.
7. Production discovery that fails closed on unlisted inputs.
8. Post-cleanup tests and semantic recertification.
9. A permanent system control index.

## Disposition policy

### ACTIVE_CERTIFIED

Files directly required by the certified runtime, daily refresh, forecast, purchase-analysis, backtest, or UIP interface.

### ACTIVE_SUPPORTING

Current standards, tests, schemas, governance, source maps, owner approvals, runbooks, and documentation required to understand or certify the active pipeline.

### ARCHIVE_READ_ONLY

The default for superseded, legacy, historical, recovery, prior-model, comparative, repair, and evidentiary materials. Archived content must be outside active discovery and retain its original path, hash, reason, lineage, and restoration instructions.

### DELETE_CANDIDATE

Deletion is considered only for verified duplicates, transient generated artifacts, empty or test-only outputs, and reproducible caches with no unique evidentiary value. Nothing is deleted automatically.

### PROTECTED_NEVER_DELETE

Standards, owner decisions, approvals, source evidence, historical observations, backtest snapshots, model and parameter versions, certification outputs, manifests, and audit lineage.

### OWNER_REVIEW_REQUIRED

Used whenever the correct disposition is uncertain.

## Required permanent control index

The final control index must be the first review point before future MTG work. It must link to:

- Certified status of each lane and the UIP connection
- Active-file allowlists
- Authoritative pipeline maps
- Source and lineage maps
- Model and parameter version registry
- Owner approval register
- Daily refresh runbook
- Backtest and recalibration runbook
- UIP interface contract
- Archive manifests
- Deletion manifests
- Prohibited-path register
- Certification and change-control history
- Restoration and rollback instructions

Repository-wide inspection should not be the normal way to rediscover the system after certification. The control index and allowlists must provide the authoritative answer.

## Active discovery rule

After certification, production scripts must use explicit manifests or allowlists. They must not recursively search the repository for a plausible file. Backup, archive, repair-input, superseded, and current-only historical-substitution paths must be blocked.

An unlisted input must cause a visible fail-closed result rather than a fallback to another file.

## Archive structure

The planned root is:

```text
archive/mtg_certified_pipeline_retirement/
```

Content will be partitioned by lane and certification version. Each archive set must contain a manifest with:

- Original path
- Archive path
- Content hash
- File role
- Disposition reason
- Replacement path, when applicable
- Dependency-scan result
- Certification version
- Archive date
- Restore instructions

## Deletion safeguards

Before deletion, each item requires:

- Exact path and content hash
- Evidence that no active dependency remains
- Confirmation that the file is duplicated or reproducible
- Confirmation that it has no unique historical or evidentiary value
- A documented replacement or regeneration procedure
- Explicit owner approval

Git history alone is not considered sufficient preservation.

## Timing

Cleanup execution is intentionally deferred until the relevant lane or UIP interface is functionally certified. Premature cleanup could remove evidence needed for backtesting, reconciliation, or methodology review.

The contract is active now, but file movement and deletion remain unauthorized.
