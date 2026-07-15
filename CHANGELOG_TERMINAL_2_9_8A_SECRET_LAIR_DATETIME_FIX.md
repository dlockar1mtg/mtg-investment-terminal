# Terminal 2.9.8a Secret Lair Datetime Fix

Normalizes Secret Lair observation and release timestamps to UTC-naive pandas
timestamps before return and product-age calculations. This resolves failures
when Master Database release dates include a trailing `Z` timezone while price
observation dates are date-only values.
