# Terminal 2.5.1a — Repository Cleanup

This release prepares the MTG Investment Terminal for its first clean Git commit.

## What it does

- Replaces the project `.gitignore` with production repository rules.
- Keeps code, tests, documentation, reference tables, and approved Product Master data in Git.
- Excludes SQLite databases, archives, source downloads, caches, dashboard outputs, analytics outputs, logs, and snapshots.
- Creates a future-facing `workspace/` structure.
- Audits files that remain visible to Git.
- Scans source files for likely embedded credentials.
- Checks for unusually large untracked or staged files.
- Does **not** move, overwrite, or delete runtime data.

## Installation

Extract this package into:

```text
C:\Users\devon\mtg_investments
```

Choose **Replace** for `.gitignore`.

The package only adds:

```text
.gitignore
scripts\repository_cleanup.py
scripts\precommit_audit.py
docs\REPOSITORY_STRUCTURE.md
workspace\README.md
.env.example
config.example.py
README_TERMINAL_2_5_1A_REPOSITORY_CLEANUP.md
```

## Run the cleanup audit

```bat
python scripts\repository_cleanup.py --apply --show-files
```

A successful result ends with:

```text
PASS: Repository is ready for the first commit.
```

Warnings about example placeholders are acceptable. Any `ERROR` should be resolved before `git add .`.

## First commit workflow

After the cleanup audit passes:

```bat
git add .
python scripts\precommit_audit.py
git status
git commit -m "Initial MTG Investment Terminal repository"
```

The pre-commit audit checks the staged files before the commit.

## Important

This release intentionally does not move the current `data/` folders. Existing code still expects those paths. Terminal 2.5.1b and 2.5.1c will introduce the publisher and controlled migration without breaking the working Terminal 2 pipeline.
