# Terminal 2.7.1a Discovery Empty-Configuration Fix

Ensures empty discovery source configurations publish valid zero-row datasets
with complete warehouse schemas. Adds an explicit regression test and skips
the optional discovery stage in the full pipeline when no source is enabled.
