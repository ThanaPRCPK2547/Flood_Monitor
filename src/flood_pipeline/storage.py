from __future__ import annotations

import geopandas as gpd
from sqlalchemy import create_engine, text


def save_flood_events_to_postgis(
    gdf: gpd.GeoDataFrame,
    database_url: str,
    schema: str,
    table: str,
) -> int:
    if gdf.empty:
        return 0

    engine = create_engine(database_url)
    
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        if schema:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    gdf.to_postgis(
        name=table,
        con=engine,
        schema=schema if schema else None,
        if_exists="append",
        index=False,
    )

    table_ref = f'"{schema}"."{table}"' if schema else f'"{table}"'
    with engine.begin() as conn:
        conn.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS "{table}_geom_gix" '
                f'ON {table_ref} USING GIST (geometry)'
            )
        )

    return int(len(gdf))
