# Secret Lair Datetime Standard

All Secret Lair analytical timestamps are parsed as UTC and converted to
timezone-naive pandas timestamps before subtraction, comparison, period
grouping, and age calculations. Exported calendar fields use ISO date strings.
