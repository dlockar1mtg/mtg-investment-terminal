# Developer Source Export

After merging and pulling the latest `main`:

```bat
git checkout main
git pull origin main
git status
python developer_export_source.py
```

The utility verifies required modules, requires a clean working tree,
exports Git-tracked files only, and saves a branch-and-commit-named ZIP
to Downloads.
