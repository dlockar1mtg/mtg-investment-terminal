# MTG Legacy Archive Policy

## Purpose

The archive removes obsolete implementation helpers from active execution
paths while retaining historical evidence and restoration capability.

## Archive-eligible files

- One-time patch scripts
- Completed migration helpers
- Superseded implementation backups
- Temporary repair scripts
- Obsolete test backups

## Files that must remain active

- Production pipeline entry points
- Certification scripts
- Semantic gates
- Governance engines
- Current policy generators
- Current tests
- Current documentation generators

## Rules

1. A file must not be archived while active references remain.
2. Every archived file records its original path, archive path, SHA-256 hash,
   reason, and timestamp.
3. Archived Python files use `.py.archived.txt` so they cannot be imported or
   collected accidentally.
4. Archived code is not authoritative.
5. Restoration requires an explicit review and a new standards-conformance
   assessment.
6. Deletion is allowed only after a later certified release confirms the file
   is unnecessary and Git history provides sufficient recovery.