#!/bin/bash
set -e

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is not set."
  echo "This script is only needed for optional Postgres/PostGIS mode."
  echo "For quick CSV-only deploy, you can skip this script."
  exit 0
fi

echo "Installing PostGIS extension..."
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS postgis;"

echo "Creating flood_risk_events table..."
psql $DATABASE_URL -f sql/init_postgis.sql

echo "Running pipeline to populate data..."
python scripts/run_pipeline.py

echo "Setup complete!"
