"""Shared datetime normalization for the Secret Lair subsystem.

All analytical timestamps are represented as UTC-naive pandas timestamps.
Input values may be date-only, timezone-naive, or timezone-aware.
"""
from __future__ import annotations

from typing import Any
import pandas as pd


def to_utc_naive_series(values: Any) -> pd.Series:
    """Parse Series-like values as UTC and remove timezone metadata."""
    parsed = pd.to_datetime(
        values,
        errors="coerce",
        utc=True,
        format="mixed",
    )
    if isinstance(parsed, pd.DatetimeIndex):
        parsed = pd.Series(
            parsed,
            index=getattr(values, "index", None),
        )
    return parsed.dt.tz_convert(None)


def to_utc_naive_scalar(value: Any) -> pd.Timestamp:
    """Parse one value as UTC and return a timezone-naive timestamp."""
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return pd.NaT
    return parsed.tz_convert(None)


def utc_naive_today() -> pd.Timestamp:
    """Return today's normalized date using the shared convention."""
    return pd.Timestamp.now(tz="UTC").tz_convert(None).normalize()


def date_string_series(values: Any) -> pd.Series:
    """Convert mixed timestamp values to nullable ISO date strings."""
    return to_utc_naive_series(values).dt.date.astype("string")
