# Secret Lair Data Population Architecture

2.9.6 reads the existing acquisition and guarded backfill layers. It reports accepted candidates and readiness but does not mutate the production registry. Registry application remains an explicit guarded backfill action after all blocking review items are resolved.
