# Model Calibration Metrics Guide

## Forecast error

- MAE measures average absolute dollar error.
- MAPE measures average absolute error relative to realized price.
- RMSE gives greater weight to large misses.
- Directional accuracy measures whether the predicted return sign was correct.

## Recommendation success

- Strong Buy succeeds at a realized return of at least 10%.
- Buy succeeds at a realized return of at least 5%.
- Watch succeeds at a nonnegative realized return.
- Hold succeeds when realized return is at least -5%.
- Avoid succeeds when realized return is negative.

These thresholds are transparent defaults for observational reporting and can
be evaluated before any later optimization release.

## Calibration readiness

- Fewer than 25 matured forecasts: insufficient
- 25 to 99 matured forecasts: initial calibration
- 100 or more matured forecasts: active calibration
