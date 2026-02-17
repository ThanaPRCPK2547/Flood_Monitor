from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd


PROVINCE_CENTROIDS: dict[str, tuple[float, float]] = {
    "Ayutthaya": (100.5686, 14.3532),
    "Bangkok": (100.5018, 13.7563),
    "Chiang Mai": (98.9853, 18.7883),
    "Chiang Rai": (99.8406, 19.9105),
    "Khon Kaen": (102.8350, 16.4419),
    "Nakhon Ratchasima": (102.0978, 14.9799),
    "Nakhon Sawan": (100.1372, 15.7047),
    "Nakhon Si Thammarat": (99.9631, 8.4304),
    "Nan": (100.7715, 18.7756),
    "Pathum Thani": (100.5250, 14.0208),
    "Phrae": (100.1417, 18.1459),
    "Songkhla": (100.5997, 7.2003),
    "Sukhothai": (99.8220, 17.0056),
    "Surat Thani": (99.3334, 9.1401),
    "Ubon Ratchathani": (104.8572, 15.2448),
}


def _minmax(series: pd.Series) -> pd.Series:
    min_val = float(series.min())
    max_val = float(series.max())
    if abs(max_val - min_val) < 1e-9:
        return pd.Series(0.0, index=series.index)
    return (series - min_val) / (max_val - min_val)


def build_province_risk_geodata(
    df: pd.DataFrame,
    min_samples_per_province: int,
    source_dataset: str,
) -> gpd.GeoDataFrame:
    grouped = (
        df.groupby("province", as_index=False)
        .agg(
            sample_count=("is_flood", "size"),
            flood_events=("is_flood", "sum"),
            rainfall_mm_mean=("rainfall_mm", "mean"),
            water_level_m_mean=("water_level_m", "mean"),
            temperature_c_mean=("temperature_c", "mean"),
            humidity_percent_mean=("humidity_percent", "mean"),
            event_start=("date", "min"),
            event_end=("date", "max"),
        )
        .copy()
    )

    grouped = grouped[grouped["sample_count"] >= min_samples_per_province].copy()

    if grouped.empty:
        return gpd.GeoDataFrame(
            columns=[
                "province",
                "sample_count",
                "flood_events",
                "flood_rate",
                "rainfall_mm_mean",
                "water_level_m_mean",
                "temperature_c_mean",
                "humidity_percent_mean",
                "risk_score",
                "event_start",
                "event_end",
                "detected_at",
                "source_dataset",
                "geometry",
            ],
            geometry="geometry",
            crs="EPSG:4326",
        )

    grouped["flood_rate"] = grouped["flood_events"] / grouped["sample_count"]

    rainfall_norm = _minmax(grouped["rainfall_mm_mean"])
    water_norm = _minmax(grouped["water_level_m_mean"])
    humidity_norm = _minmax(grouped["humidity_percent_mean"])

    grouped["risk_score"] = (
        0.40 * water_norm
        + 0.30 * rainfall_norm
        + 0.20 * grouped["flood_rate"]
        + 0.10 * humidity_norm
    ).clip(lower=0.0, upper=1.0)

    grouped["lon"] = grouped["province"].map(
        lambda p: PROVINCE_CENTROIDS.get(p, (np.nan, np.nan))[0]
    )
    grouped["lat"] = grouped["province"].map(
        lambda p: PROVINCE_CENTROIDS.get(p, (np.nan, np.nan))[1]
    )
    grouped = grouped.dropna(subset=["lon", "lat"]).copy()

    grouped["detected_at"] = pd.Timestamp.utcnow()
    grouped["source_dataset"] = source_dataset

    gdf = gpd.GeoDataFrame(
        grouped,
        geometry=gpd.points_from_xy(grouped["lon"], grouped["lat"]),
        crs="EPSG:4326",
    )

    return gdf[
        [
            "province",
            "sample_count",
            "flood_events",
            "flood_rate",
            "rainfall_mm_mean",
            "water_level_m_mean",
            "temperature_c_mean",
            "humidity_percent_mean",
            "risk_score",
            "event_start",
            "event_end",
            "detected_at",
            "source_dataset",
            "geometry",
        ]
    ]
