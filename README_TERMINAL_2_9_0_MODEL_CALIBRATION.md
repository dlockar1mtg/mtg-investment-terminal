# Terminal 2.9.0 — Model Calibration Engine

Terminal 2.9.0 adds the observational feedback loop for forecasts and
recommendations.

## Publish

```bat
python terminal2_publish_model_calibration.py
```

## Validate

```bat
python terminal2_model_calibration_validate.py
```

The first run archives the current 6-, 12-, 36-, and 60-month forecasts. No
performance metric is calculated until the corresponding target date has
passed and a realized price is available.

The engine is observational. It does not change model weights.
