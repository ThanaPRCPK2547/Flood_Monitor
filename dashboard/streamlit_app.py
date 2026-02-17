from __future__ import annotations

import os

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st
from sqlalchemy import create_engine


st.set_page_config(page_title="Flood Risk Dashboard", layout="wide")
st.title("Thailand Flood Risk Dashboard (CSV-based)")

DATABASE_URL = os.getenv("DATABASE_URL", "")
SCHEMA = os.getenv("FLOOD_SCHEMA", "public")
TABLE = os.getenv("FLOOD_TABLE", "flood_risk_events")

if not DATABASE_URL:
    st.error("Missing DATABASE_URL environment variable")
    st.stop()


@st.cache_data(ttl=900)
def load_flood_events() -> gpd.GeoDataFrame:
    engine = create_engine(DATABASE_URL)
    query = f"""
        SELECT
            province,
            sample_count,
            flood_events,
            flood_rate,
            rainfall_mm_mean,
            water_level_m_mean,
            temperature_c_mean,
            humidity_percent_mean,
            risk_score,
            event_start,
            event_end,
            detected_at,
            source_dataset,
            geometry
        FROM {SCHEMA}.{TABLE}
        WHERE detected_at >= NOW() - INTERVAL '90 days'
    """
    return gpd.read_postgis(query, con=engine, geom_col="geometry")


try:
    gdf = load_flood_events()
except Exception as exc:
    st.exception(exc)
    st.stop()

if gdf.empty:
    st.warning("No flood risk records in the last 90 days.")
    st.stop()

latest = (
    gdf.sort_values("detected_at", ascending=False)
    .drop_duplicates(subset=["province"])
    .reset_index(drop=True)
)

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("Provinces monitored", f"{len(latest):,}")
metric_col2.metric("Average risk score", f"{latest['risk_score'].mean():.2f}")
metric_col3.metric("High risk provinces", f"{int((latest['risk_score'] >= 0.70).sum()):,}")

points = latest.to_crs("EPSG:4326").copy()
points["lon"] = points.geometry.x
points["lat"] = points.geometry.y
points["weight"] = (points["risk_score"] * points["sample_count"]).clip(lower=0.01)

view_state = pdk.ViewState(
    latitude=float(points["lat"].mean()),
    longitude=float(points["lon"].mean()),
    zoom=5,
    pitch=35,
)

heat_layer = pdk.Layer(
    "HeatmapLayer",
    data=points[["lat", "lon", "weight"]],
    get_position="[lon, lat]",
    get_weight="weight",
    radiusPixels=70,
)

scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=points,
    get_position="[lon, lat]",
    get_radius="risk_score * 12000",
    get_fill_color="[255, 120 - risk_score * 80, 60, 180]",
    pickable=True,
)

st.pydeck_chart(
    pdk.Deck(
        layers=[heat_layer, scatter_layer],
        initial_view_state=view_state,
        tooltip={"text": "{province}\nRisk: {risk_score}\nFlood rate: {flood_rate}"},
    )
)

st.subheader("Province Risk Ranking")
st.dataframe(
    latest[
        [
            "province",
            "risk_score",
            "flood_rate",
            "flood_events",
            "sample_count",
            "rainfall_mm_mean",
            "water_level_m_mean",
            "event_start",
            "event_end",
            "detected_at",
        ]
    ].sort_values(["risk_score", "flood_rate"], ascending=False),
    use_container_width=True,
)
