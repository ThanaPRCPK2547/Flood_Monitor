from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from sentinelhub import (
    BBox,
    CRS,
    DataCollection,
    MimeType,
    SHConfig,
    SentinelHubRequest,
    bbox_to_dimensions,
)

from flood_pipeline.config import PipelineSettings


EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B03", "B11", "dataMask"],
    output: { bands: 3, sampleType: "FLOAT32" }
  };
}

function evaluatePixel(sample) {
  return [sample.B03, sample.B11, sample.dataMask];
}
"""


def _resolve_crs(crs_text: str) -> CRS:
    normalized = crs_text.strip().upper()
    if normalized in {"EPSG:4326", "WGS84"}:
        return CRS.WGS84
    if normalized.startswith("EPSG:"):
        epsg_code = int(normalized.split(":")[1])
        return CRS(epsg_code)
    if normalized.isdigit():
        return CRS(int(normalized))
    raise ValueError(f"Unsupported CRS format: {crs_text}")


def download_sentinel_weekly_composite(
    settings: PipelineSettings,
    output_dir: Path,
    start_date: date,
    end_date: date,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    sh_config = SHConfig()
    sh_config.sh_client_id = settings.sh_client_id
    sh_config.sh_client_secret = settings.sh_client_secret

    aoi_crs = _resolve_crs(settings.aoi.crs)
    bbox = BBox(bbox=settings.aoi.bbox, crs=aoi_crs)
    size = bbox_to_dimensions(bbox=bbox, resolution=settings.ingestion.resolution_m)

    request = SentinelHubRequest(
        evalscript=EVALSCRIPT,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A,
                time_interval=(start_date.isoformat(), end_date.isoformat()),
                maxcc=settings.ingestion.max_cloud_coverage,
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        size=size,
        config=sh_config,
    )

    data = request.get_data()[0]

    if data.ndim != 3:
        raise RuntimeError("Unexpected Sentinel Hub output shape.")
    if data.shape[0] == 3 and data.shape[2] != 3:
        data = np.moveaxis(data, 0, -1)

    output_path = output_dir / f"sentinel2_{settings.aoi.name}_{start_date}_{end_date}.tif"
    transform = from_bounds(*settings.aoi.bbox, width=data.shape[1], height=data.shape[0])

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=3,
        dtype="float32",
        crs=settings.aoi.crs,
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(data[:, :, 0].astype("float32"), 1)
        dst.write(data[:, :, 1].astype("float32"), 2)
        dst.write(data[:, :, 2].astype("float32"), 3)

    return output_path
