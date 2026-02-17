from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask, shapes
from shapely.geometry import shape


def compute_mndwi(green_band: np.ndarray, swir_band: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return (green_band - swir_band) / (green_band + swir_band + eps)


def _polygon_mean_mndwi(gdf: gpd.GeoDataFrame, mndwi: np.ndarray, transform) -> list[float]:
    means: list[float] = []
    for geom in gdf.geometry:
        mask = geometry_mask([geom], out_shape=mndwi.shape, transform=transform, invert=True)
        values = mndwi[mask]
        means.append(float(np.nanmean(values)) if values.size else float("nan"))
    return means


def extract_flood_polygons(
    input_raster: Path,
    output_mask_tif: Path,
    output_geojson: Path,
    mndwi_threshold: float,
    min_polygon_area_sqkm: float,
) -> gpd.GeoDataFrame:
    output_mask_tif.parent.mkdir(parents=True, exist_ok=True)
    output_geojson.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(input_raster) as src:
        green = src.read(1).astype("float32")
        swir = src.read(2).astype("float32")
        data_mask = src.read(3).astype("float32")

        mndwi = compute_mndwi(green, swir)
        water_mask = ((mndwi > mndwi_threshold) & (data_mask > 0)).astype("uint8")

        profile = src.profile.copy()
        profile.update(count=1, dtype="uint8", nodata=0, compress="deflate")

        with rasterio.open(output_mask_tif, "w", **profile) as dst:
            dst.write(water_mask, 1)

        geoms = [
            {"geometry": shape(geom), "water": int(val)}
            for geom, val in shapes(water_mask, mask=water_mask == 1, transform=src.transform)
            if int(val) == 1
        ]

        if not geoms:
            empty = gpd.GeoDataFrame(
                columns=["water", "area_sqkm", "mean_mndwi", "detected_at", "source_raster", "geometry"],
                geometry="geometry",
                crs=src.crs,
            )
            return empty

        gdf = gpd.GeoDataFrame(geoms, geometry="geometry", crs=src.crs)
        utm_crs = gdf.estimate_utm_crs() or "EPSG:3857"
        gdf["area_sqkm"] = gdf.to_crs(utm_crs).geometry.area / 1_000_000
        gdf = gdf[gdf["area_sqkm"] >= min_polygon_area_sqkm].copy()

        if gdf.empty:
            return gdf

        gdf["mean_mndwi"] = _polygon_mean_mndwi(gdf, mndwi, src.transform)
        gdf["detected_at"] = pd.Timestamp.utcnow()
        gdf["source_raster"] = input_raster.name

    gdf.to_file(output_geojson, driver="GeoJSON")
    return gdf
