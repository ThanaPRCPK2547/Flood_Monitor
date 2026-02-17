CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS public.flood_risk_events (
    province TEXT,
    sample_count BIGINT,
    flood_events BIGINT,
    flood_rate DOUBLE PRECISION,
    rainfall_mm_mean DOUBLE PRECISION,
    water_level_m_mean DOUBLE PRECISION,
    temperature_c_mean DOUBLE PRECISION,
    humidity_percent_mean DOUBLE PRECISION,
    risk_score DOUBLE PRECISION,
    event_start DATE,
    event_end DATE,
    detected_at TIMESTAMPTZ,
    source_dataset TEXT,
    geometry geometry(Point, 4326)
);

CREATE INDEX IF NOT EXISTS flood_risk_events_geom_gix
    ON public.flood_risk_events
    USING GIST (geometry);
