# Terminal 2.9.0a Target-Date Compatibility Fix

Fixes forecast target-date construction under pandas 3.x by avoiding the
`.dt` accessor on an object-typed Series of timestamp and DateOffset results.
Adds a regression test for 6-, 12-, 36-, and 60-month forecast horizons.
