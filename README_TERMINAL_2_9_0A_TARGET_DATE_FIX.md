# Terminal 2.9.0a — Target-Date Compatibility Fix

Apply this patch on top of Terminal 2.9.0 before committing the release.

It replaces object-Series date arithmetic with explicit per-horizon timestamp
calculation, preserving the intended target dates on pandas 3.x and Python 3.14.
