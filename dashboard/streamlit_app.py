from __future__ import annotations

import glob
import os
from pathlib import Path
import sys
from datetime import date, timedelta

import geopandas as gpd
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Load environment variables
load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from flood_pipeline.csv_ingestion import load_mockup_flood_dataset
    from flood_pipeline.csv_processing import (
        PROVINCE_CENTROIDS,
        build_province_risk_geodata,
    )

    CSV_FALLBACK_AVAILABLE = True
except Exception:
    PROVINCE_CENTROIDS = {}
    CSV_FALLBACK_AVAILABLE = False

st.set_page_config(page_title="Flood Risk Dashboard", layout="wide")
st.title("Thailand Flood Risk Dashboard")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SCHEMA = os.getenv("FLOOD_SCHEMA", "public").strip()
TABLE = os.getenv("FLOOD_TABLE", "flood_risk_events").strip()
LOCAL_GEOJSON_GLOB = os.getenv("FLOOD_LOCAL_GEOJSON_GLOB", "data/output/flood_risk_*.geojson").strip()
LOCAL_CSV_PATH = os.getenv("FLOOD_DATASET_PATH", "data/thailand_flood_sample.csv").strip()
LOOKBACK_DAYS = int(os.getenv("FLOOD_LOOKBACK_DAYS", "90"))
MIN_SAMPLES_PER_PROVINCE = int(os.getenv("FLOOD_MIN_SAMPLES_PER_PROVINCE", "300"))
REQUIRED_COLUMNS = {
    "province",
    "sample_count",
    "flood_events",
    "flood_rate",
    "rainfall_mm_mean",
    "water_level_m_mean",
    "risk_score",
    "detected_at",
    "geometry",
}


def _risk_to_rgb(risk: float) -> tuple[int, int, int]:
    """Map normalized risk (0..1) to a yellow->green->cyan->purple gradient."""
    value = max(0.0, min(1.0, float(risk)))
    anchors = [
        (0.00, (245, 240, 24)),
        (0.25, (122, 233, 28)),
        (0.50, (42, 201, 92)),
        (0.75, (64, 150, 205)),
        (1.00, (120, 76, 190)),
    ]

    for i in range(len(anchors) - 1):
        left_pos, left_color = anchors[i]
        right_pos, right_color = anchors[i + 1]
        if left_pos <= value <= right_pos:
            ratio = (value - left_pos) / (right_pos - left_pos)
            return tuple(
                int(round(left + (right - left) * ratio))
                for left, right in zip(left_color, right_color)
            )

    return anchors[-1][1]


def _resolve_csv_path(path_str: str) -> Path:
    csv_path = Path(path_str)
    if not csv_path.is_absolute():
        csv_path = ROOT_DIR / csv_path
    return csv_path


def _minmax_numeric(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    min_val = values.min()
    max_val = values.max()
    if pd.isna(min_val) or pd.isna(max_val) or abs(max_val - min_val) < 1e-9:
        return pd.Series(0.0, index=series.index)
    return (values - min_val) / (max_val - min_val)


@st.cache_data(ttl=900)
def load_event_level_dataset(path_str: str) -> pd.DataFrame:
    if not CSV_FALLBACK_AVAILABLE:
        raise RuntimeError("CSV event-level loader is unavailable")

    csv_path = _resolve_csv_path(path_str)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV dataset file not found: {csv_path}")

    df = pd.read_csv(csv_path, parse_dates=["date"])
    required = {
        "date",
        "province",
        "rainfall_mm",
        "water_level_m",
        "temperature_c",
        "humidity_percent",
        "is_flood",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"CSV dataset missing required columns: {sorted(missing)}")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["province"] = df["province"].astype(str).str.strip()
    for col in [
        "rainfall_mm",
        "water_level_m",
        "temperature_c",
        "humidity_percent",
        "is_flood",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(
        subset=["date", "province", "rainfall_mm", "water_level_m", "humidity_percent", "is_flood"]
    )
    df["is_flood"] = df["is_flood"].astype(int).clip(lower=0, upper=1)

    # Attach centroid and create deterministic jitter so each event is not collapsed to one point.
    df["lon_center"] = df["province"].map(
        lambda p: PROVINCE_CENTROIDS.get(p, (np.nan, np.nan))[0]
    )
    df["lat_center"] = df["province"].map(
        lambda p: PROVINCE_CENTROIDS.get(p, (np.nan, np.nan))[1]
    )
    df = df.dropna(subset=["lon_center", "lat_center"]).copy()

    rng = np.random.default_rng(42)
    df["lon"] = df["lon_center"] + rng.normal(loc=0.0, scale=0.12, size=len(df))
    df["lat"] = df["lat_center"] + rng.normal(loc=0.0, scale=0.10, size=len(df))
    df["lon"] = df["lon"].clip(97.0, 106.0)
    df["lat"] = df["lat"].clip(5.0, 21.0)

    rain_norm = _minmax_numeric(df["rainfall_mm"])
    water_norm = _minmax_numeric(df["water_level_m"])
    humidity_norm = _minmax_numeric(df["humidity_percent"])
    temp_norm = _minmax_numeric(df["temperature_c"])
    df["event_risk_score"] = (
        0.42 * water_norm
        + 0.30 * rain_norm
        + 0.15 * df["is_flood"]
        + 0.08 * humidity_norm
        + 0.05 * temp_norm
    ).clip(lower=0.0, upper=1.0)

    df["event_date"] = df["date"].dt.date
    df["event_hour"] = df["date"].dt.hour.astype(int)
    df["event_time_label"] = df["date"].dt.strftime("%Y-%m-%d %H:%M")
    return df


@st.cache_data(ttl=900)
def load_flood_events_from_db() -> gpd.GeoDataFrame:
    if not DATABASE_URL:
        raise ValueError("Missing DATABASE_URL environment variable")

    engine = create_engine(DATABASE_URL)
    table_name = f'"{SCHEMA}"."{TABLE}"' if SCHEMA else f'"{TABLE}"'

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
        FROM {table_name}
        WHERE detected_at >= NOW() - INTERVAL '{LOOKBACK_DAYS} days'
    """
    return gpd.read_postgis(query, con=engine, geom_col="geometry")


def _find_latest_geojson() -> Path | None:
    pattern_path = Path(LOCAL_GEOJSON_GLOB)
    if pattern_path.is_absolute():
        files = sorted(
            [Path(p) for p in glob.glob(LOCAL_GEOJSON_GLOB)],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    else:
        files = sorted(
            ROOT_DIR.glob(LOCAL_GEOJSON_GLOB),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    return files[0] if files else None


@st.cache_data(ttl=900)
def load_flood_events_from_geojson(path_str: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path_str)
    for col in ["event_start", "event_end", "detected_at"]:
        if col in gdf.columns:
            gdf[col] = pd.to_datetime(gdf[col], errors="coerce")
    return gdf


def _resolve_date_range() -> tuple[date, date]:
    start_env = os.getenv("START_DATE", "").strip()
    end_env = os.getenv("END_DATE", "").strip()
    if start_env and end_env:
        return date.fromisoformat(start_env), date.fromisoformat(end_env)
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    return start_date, end_date


@st.cache_data(ttl=900)
def load_flood_events_from_csv(path_str: str) -> gpd.GeoDataFrame:
    if not CSV_FALLBACK_AVAILABLE:
        raise RuntimeError("CSV fallback modules are unavailable")

    csv_path = Path(path_str)
    if not csv_path.is_absolute():
        csv_path = ROOT_DIR / csv_path
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV dataset file not found: {csv_path}")

    start_date, end_date = _resolve_date_range()
    raw_df, _, _ = load_mockup_flood_dataset(
        csv_path=csv_path,
        start_date=start_date,
        end_date=end_date,
    )
    return build_province_risk_geodata(
        df=raw_df,
        min_samples_per_province=MIN_SAMPLES_PER_PROVINCE,
        source_dataset=csv_path.name,
    )


def load_flood_events() -> tuple[gpd.GeoDataFrame, str]:
    db_error: Exception | None = None
    geojson_error: Exception | None = None

    if DATABASE_URL:
        try:
            return load_flood_events_from_db(), "database"
        except Exception as exc:  # pragma: no cover - runtime fallback
            db_error = exc

    latest_geojson = _find_latest_geojson()
    if latest_geojson:
        try:
            return load_flood_events_from_geojson(str(latest_geojson)), f"geojson:{latest_geojson}"
        except Exception as exc:  # pragma: no cover - runtime fallback
            geojson_error = exc

    if CSV_FALLBACK_AVAILABLE:
        return load_flood_events_from_csv(LOCAL_CSV_PATH), f"csv:{LOCAL_CSV_PATH}"

    if db_error or geojson_error:
        raise RuntimeError(
            "Failed to load data from database/GeoJSON and CSV fallback is unavailable."
        ) from (geojson_error or db_error)

    raise RuntimeError(
        "No data source available. Set DATABASE_URL, provide data/output GeoJSON, or configure FLOOD_DATASET_PATH."
    )


try:
    gdf, data_source = load_flood_events()
except Exception as exc:
    st.error("Failed to load flood risk data.")
    st.exception(exc)
    st.stop()

event_df: pd.DataFrame | None = None
event_error: Exception | None = None
if CSV_FALLBACK_AVAILABLE:
    try:
        event_df = load_event_level_dataset(LOCAL_CSV_PATH)
    except Exception as exc:  # pragma: no cover - runtime fallback
        event_error = exc

if gdf.empty and (event_df is None or event_df.empty):
    st.warning(f"No flood risk records found from `{data_source}`.")
    st.stop()

if not gdf.empty:
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    missing_columns = REQUIRED_COLUMNS.difference(gdf.columns)
    if missing_columns:
        st.error(f"Data source is missing required columns: {sorted(missing_columns)}")
        st.stop()
    latest = (
        gdf.sort_values("detected_at", ascending=False)
        .drop_duplicates(subset=["province"])
        .reset_index(drop=True)
    )
else:
    latest = pd.DataFrame(
        columns=[
            "province",
            "sample_count",
            "flood_events",
            "flood_rate",
            "rainfall_mm_mean",
            "water_level_m_mean",
            "risk_score",
            "event_start",
            "event_end",
            "detected_at",
            "geometry",
        ]
    )

st.caption(f"Data source: `{data_source}`")

with st.sidebar:
    st.markdown("## DASH - FLOOD DATA APP")
    st.markdown(
        "Select different days using the date picker or by selecting location/time filters."
    )

if event_df is not None and not event_df.empty:
    date_candidates = sorted(event_df["event_date"].dropna().unique().tolist())
    default_date = date_candidates[-1] if date_candidates else date.today()
    min_date = date_candidates[0] if date_candidates else default_date
    max_date = date_candidates[-1] if date_candidates else default_date

    province_options = sorted(event_df["province"].dropna().astype(str).unique().tolist())

    has_hour_precision = (
        event_df["date"].dt.hour.nunique() > 1
        or event_df["date"].dt.minute.nunique() > 1
        or event_df["date"].dt.second.nunique() > 1
    )
    hour_options = (
        sorted(event_df["event_hour"].dropna().astype(int).unique().tolist())
        if has_hour_precision
        else []
    )

    with st.sidebar:
        selected_date = st.date_input(
            "Select date",
            value=default_date,
            min_value=min_date,
            max_value=max_date,
        )
        selected_location = st.selectbox(
            "Select a location",
            options=["All locations", *province_options],
            index=0,
        )
        if hour_options:
            selected_hours = st.multiselect(
                "Select certain hours",
                options=hour_options,
                default=hour_options,
                format_func=lambda h: f"{h:02d}:00",
            )
        else:
            selected_hours = []
            st.multiselect(
                "Select certain hours",
                options=[],
                default=[],
                disabled=True,
                placeholder="No hourly data in current dataset",
            )
        max_map_points = st.slider(
            "Max points on map",
            min_value=1000,
            max_value=60000,
            value=15000,
            step=1000,
        )

    event_mask = event_df["event_date"] == selected_date
    if selected_location != "All locations":
        event_mask &= event_df["province"] == selected_location
    if hour_options and selected_hours and len(selected_hours) < len(hour_options):
        event_mask &= event_df["event_hour"].isin(selected_hours)
    filtered_events = event_df[event_mask].copy()

    selected_day_total = int((event_df["event_date"] == selected_date).sum())
    if not hour_options or len(selected_hours) == len(hour_options):
        hour_summary = "All"
    elif selected_hours:
        hour_summary = ", ".join(f"{h:02d}" for h in selected_hours)
    else:
        hour_summary = "None"

    with st.sidebar:
        st.markdown(f"**Total records on {selected_date.isoformat()}:** {selected_day_total:,}")
        st.markdown(f"**Records in selection:** {len(filtered_events):,}")
        st.markdown(f"**{selected_date.isoformat()} - showing hour(s):** {hour_summary}")
        st.markdown(f"**Source:** `csv:{_resolve_csv_path(LOCAL_CSV_PATH)}`")

    if filtered_events.empty:
        st.warning("No event rows matched your current filter selection.")
        st.stop()

    filtered_latest = (
        filtered_events.groupby("province", as_index=False)
        .agg(
            sample_count=("is_flood", "size"),
            flood_events=("is_flood", "sum"),
            rainfall_mm_mean=("rainfall_mm", "mean"),
            water_level_m_mean=("water_level_m", "mean"),
            risk_score=("event_risk_score", "mean"),
            detected_at=("date", "max"),
            lon=("lon_center", "mean"),
            lat=("lat_center", "mean"),
        )
        .copy()
    )
    filtered_latest["flood_rate"] = filtered_latest["flood_events"] / filtered_latest["sample_count"]
    filtered_latest["event_start"] = selected_date
    filtered_latest["event_end"] = selected_date

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Provinces monitored", f"{len(filtered_latest):,}")
    metric_col2.metric("Average risk score", f"{filtered_latest['risk_score'].mean():.2f}")
    metric_col3.metric(
        "High risk provinces", f"{int((filtered_latest['risk_score'] >= 0.70).sum()):,}"
    )

    map_events = filtered_events.copy()
    total_selected_points = len(map_events)
    if total_selected_points > max_map_points:
        map_events = map_events.sample(n=max_map_points, random_state=42).copy()

    map_points = map_events[
        [
            "province",
            "event_risk_score",
            "rainfall_mm",
            "water_level_m",
            "event_time_label",
            "is_flood",
            "lon",
            "lat",
        ]
    ].copy()
    map_points["risk_score"] = map_points["event_risk_score"]
    map_points["risk_pct"] = (map_points["risk_score"] * 100).round(1)
    map_points["risk_label"] = map_points["risk_pct"].map(lambda x: f"{x:.1f}%")
    map_points["flood_label"] = map_points["is_flood"].map(
        lambda x: "Flood event" if int(x) == 1 else "No flood"
    )
    map_points["radius_m"] = (500 + map_points["risk_score"] * 2200).round(0).astype(int)
    map_points["alpha"] = (
        70 + map_points["risk_score"] * 110 + map_points["is_flood"] * 45
    ).clip(70, 230).round(0).astype(int)
    map_points["border"] = (100 + map_points["risk_score"] * 90).round(0).astype(int)

    colors = map_points["risk_score"].map(_risk_to_rgb)
    map_points["r"] = colors.map(lambda c: int(c[0]))
    map_points["g"] = colors.map(lambda c: int(c[1]))
    map_points["b"] = colors.map(lambda c: int(c[2]))
    map_points["rainfall_mm"] = map_points["rainfall_mm"].round(2)
    map_points["water_level_m"] = map_points["water_level_m"].round(2)
    points_data = map_points[
        [
            "province",
            "risk_score",
            "risk_label",
            "flood_label",
            "rainfall_mm",
            "water_level_m",
            "event_time_label",
            "lon",
            "lat",
            "radius_m",
            "alpha",
            "border",
            "r",
            "g",
            "b",
        ]
    ].to_dict("records")

    label_df = filtered_latest.copy()
    label_df["risk_label"] = (label_df["risk_score"] * 100).round(1).map(lambda x: f"{x:.1f}%")
    label_colors = label_df["risk_score"].map(_risk_to_rgb)
    label_df["r"] = label_colors.map(lambda c: int(c[0]))
    label_df["g"] = label_colors.map(lambda c: int(c[1]))
    label_df["b"] = label_colors.map(lambda c: int(c[2]))
    top_risk_labels = label_df.nlargest(5, "risk_score").copy()
    top_risk_labels["label"] = (
        top_risk_labels["province"] + " (" + top_risk_labels["risk_label"] + ")"
    )
    labels_data = top_risk_labels[
        ["label", "lon", "lat", "r", "g", "b"]
    ].to_dict("records")

    view_state = {
        "latitude": float(map_points["lat"].mean()),
        "longitude": float(map_points["lon"].mean()),
        "zoom": 5,
        "pitch": 18,
    }

    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=points_data,
        get_position="[lon, lat]",
        get_radius="radius_m",
        radius_min_pixels=2,
        radius_max_pixels=20,
        stroked=True,
        line_width_min_pixels=0.8,
        get_fill_color="[r, g, b, alpha]",
        get_line_color="[255, 255, 255, border]",
        pickable=True,
        auto_highlight=True,
    )

    text_layer = pdk.Layer(
        "TextLayer",
        data=labels_data,
        get_position="[lon, lat]",
        get_text="label",
        get_size=14,
        get_color="[235, 241, 255, 230]",
        get_alignment_baseline="'bottom'",
        get_pixel_offset="[0, -14]",
        pickable=False,
    )

    st.pydeck_chart(
        pdk.Deck(
            layers=[scatter_layer, text_layer],
            map_style="dark",
            initial_view_state=view_state,
            tooltip={
                "text": "{province}\nRisk score: {risk_label}\nRainfall: {rainfall_mm} mm\nWater: {water_level_m} m\nStatus: {flood_label}\nTime: {event_time_label}"
            },
        )
    )

    if total_selected_points > max_map_points:
        st.caption(
            f"Showing {len(points_data):,} of {total_selected_points:,} event rows on map (downsampled)."
        )
    else:
        st.caption(f"Showing {len(points_data):,} event rows on map.")
else:
    if event_error is not None:
        st.warning("CSV event-level mode is unavailable, fallback to aggregated province view.")

    filtered_latest = latest.copy()
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Provinces monitored", f"{len(filtered_latest):,}")
    metric_col2.metric("Average risk score", f"{filtered_latest['risk_score'].mean():.2f}")
    metric_col3.metric(
        "High risk provinces", f"{int((filtered_latest['risk_score'] >= 0.70).sum()):,}"
    )

    points = filtered_latest.to_crs("EPSG:4326").dropna(subset=["geometry"]).copy()
    if points.empty:
        st.warning("No valid geometry points to display on map.")
        st.stop()

    points["lon"] = points.geometry.x
    points["lat"] = points.geometry.y
    map_points = points[["province", "risk_score", "flood_rate", "lon", "lat"]].copy()
    map_points["risk_pct"] = (map_points["risk_score"] * 100).round(1)
    map_points["radius_m"] = (4500 + map_points["risk_score"] * 18000).round(0).astype(int)
    map_points["alpha"] = (160 + map_points["risk_score"] * 90).round(0).astype(int)
    map_points["border"] = (110 + map_points["risk_score"] * 120).round(0).astype(int)
    map_points["risk_label"] = map_points["risk_pct"].map(lambda x: f"{x:.1f}%")
    colors = map_points["risk_score"].map(_risk_to_rgb)
    map_points["r"] = colors.map(lambda c: int(c[0]))
    map_points["g"] = colors.map(lambda c: int(c[1]))
    map_points["b"] = colors.map(lambda c: int(c[2]))
    points_data = map_points.to_dict("records")

    view_state = {
        "latitude": float(points["lat"].mean()),
        "longitude": float(points["lon"].mean()),
        "zoom": 5,
        "pitch": 18,
    }
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=points_data,
        get_position="[lon, lat]",
        get_radius="radius_m",
        radius_min_pixels=5,
        radius_max_pixels=35,
        stroked=True,
        line_width_min_pixels=1.2,
        get_fill_color="[r, g, b, alpha]",
        get_line_color="[255, 255, 255, border]",
        pickable=True,
        auto_highlight=True,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=[scatter_layer],
            map_style="dark",
            initial_view_state=view_state,
            tooltip={"text": "{province}\nRisk score: {risk_label}"},
        )
    )
    st.caption("Showing aggregated province-level points.")

st.caption("Scatter color scale: Yellow (low risk) -> Purple (high risk)")
st.markdown(
    """
<div style="margin-top:-6px;margin-bottom:14px;">
  <div style="
    height:12px;
    border-radius:999px;
    background: linear-gradient(90deg, rgb(245,240,24) 0%, rgb(122,233,28) 25%, rgb(42,201,92) 50%, rgb(64,150,205) 75%, rgb(120,76,190) 100%);
  "></div>
  <div style="display:flex;justify-content:space-between;font-size:12px;opacity:0.8;">
    <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.subheader("Province Risk Ranking")
ranking_df = filtered_latest[
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
].sort_values(["risk_score", "flood_rate"], ascending=False)
st.dataframe(ranking_df, width="stretch")
