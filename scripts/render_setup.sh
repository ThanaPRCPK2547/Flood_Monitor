#!/bin/bash
set -e

echo "Installing PostGIS extension..."
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS postgis;"

echo "Creating flood_risk_events table..."
psql $DATABASE_URL -f sql/init_postgis.sql

echo "Running pipeline to populate data..."
python scripts/run_pipeline.py

echo "Setup complete!"
