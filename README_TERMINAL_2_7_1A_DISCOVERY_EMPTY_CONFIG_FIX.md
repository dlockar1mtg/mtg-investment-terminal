# Terminal 2.7.1a — Discovery Empty-Configuration Fix

The standalone discovery command now publishes and validates seven empty
datasets when no sources are configured. `terminal2_run_all.py` skips discovery
when no source is enabled and continues with the rest of the pipeline.
