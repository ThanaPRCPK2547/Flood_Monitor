from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "date",
    "province",
    "rainfall_mm",
    "water_level_m",
    "temperature_c",
    "humidity_percent",
    "is_flood",
}


def load_mockup_flood_dataset(
    csv_path: Path,
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame, date, date]:
    df = pd.read_csv(csv_path, parse_dates=["date"])

    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {sorted(missing)}")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["province"] = df["province"].astype(str).str.strip()

    numeric_cols = [
        "rainfall_mm",
        "water_level_m",
        "temperature_c",
        "humidity_percent",
        "is_flood",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "province", "rainfall_mm", "water_level_m", "is_flood"])
    df["is_flood"] = df["is_flood"].astype(int).clip(lower=0, upper=1)

    filtered = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy()
    effective_start = start_date
    effective_end = end_date

    if filtered.empty:
        latest_date = df["date"].max()
        effective_end = latest_date
        effective_start = latest_date - timedelta(days=6)
        filtered = df[(df["date"] >= effective_start) & (df["date"] <= effective_end)].copy()

    return filtered, effective_start, effective_end
