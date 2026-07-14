# Model Calibration Architecture

## Forecast vintages

Each run archives the model's forecast before later prices are known. The
archive key is forecast run, product, and horizon.

## Maturity

A forecast matures only after its target date. The engine selects the first
available observed market price on or after that target date, within a
45-day tolerance. Forecasts without a qualifying realized price remain
explicitly unresolved.

## Metrics

- Mean absolute price error
- Mean absolute percentage error
- Root mean squared error
- Return error
- Directional accuracy
- Recommendation hit rate
- Observed versus predicted loss frequency

## Safety

Terminal 2.9.0 reports performance but never modifies forecast or
recommendation weights. Weight optimization is reserved for later releases.
