from __future__ import annotations

from pathlib import Path

from flood_pipeline.config import load_settings
from flood_pipeline.csv_ingestion import load_mockup_flood_dataset
from flood_pipeline.csv_processing import build_province_risk_geodata
from flood_pipeline.storage import save_flood_events_to_postgis


def run_pipeline(config_path: str | Path = "config/settings.yaml") -> dict:
    settings = load_settings(config_path)

    settings.paths.output_dir.mkdir(parents=True, exist_ok=True)

    raw_df, effective_start, effective_end = load_mockup_flood_dataset(
        csv_path=settings.data_source.csv_path,
        start_date=settings.start_date,
        end_date=settings.end_date,
    )

    flood_gdf = build_province_risk_geodata(
        df=raw_df,
        min_samples_per_province=settings.processing.min_samples_per_province,
        source_dataset=settings.data_source.csv_path.name,
    )

    output_geojson = settings.paths.output_dir / f"flood_risk_{effective_start}_{effective_end}.geojson"
    if not flood_gdf.empty:
        flood_gdf.to_file(output_geojson, driver="GeoJSON")

    inserted_rows = save_flood_events_to_postgis(
        gdf=flood_gdf,
        database_url=settings.database_url,
        schema=settings.storage.schema,
        table=settings.storage.table,
    )

    return {
        "dataset": str(settings.data_source.csv_path),
        "start_date": effective_start.isoformat(),
        "end_date": effective_end.isoformat(),
        "records_used": int(len(raw_df)),
        "province_points": int(len(flood_gdf)),
        "rows_inserted": inserted_rows,
        "flood_geojson": str(output_geojson),
    }
