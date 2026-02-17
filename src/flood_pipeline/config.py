from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import os

import yaml
from dotenv import load_dotenv


@dataclass
class DataSourceConfig:
    mode: str
    csv_path: Path


@dataclass
class ProcessingConfig:
    min_samples_per_province: int


@dataclass
class StorageConfig:
    schema: str
    table: str


@dataclass
class PathsConfig:
    output_dir: Path


@dataclass
class PipelineSettings:
    data_source: DataSourceConfig
    processing: ProcessingConfig
    storage: StorageConfig
    paths: PathsConfig
    database_url: str
    start_date: date
    end_date: date


def _resolve_date_range() -> tuple[date, date]:
    today = date.today()
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")

    if start_env and end_env:
        start_date = date.fromisoformat(start_env)
        end_date = date.fromisoformat(end_env)
        if start_date > end_date:
            raise ValueError("START_DATE must be <= END_DATE")
        return start_date, end_date

    end_date = today
    start_date = today - timedelta(days=7)
    return start_date, end_date


def load_settings(config_path: str | Path = "config/settings.yaml") -> PipelineSettings:
    load_dotenv()

    with Path(config_path).open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    start_date, end_date = _resolve_date_range()

    data_source_cfg = cfg.get("data_source", {})
    csv_path_str = os.getenv("FLOOD_DATASET_PATH") or data_source_cfg.get("csv_path")
    if not csv_path_str:
        raise ValueError("FLOOD_DATASET_PATH must be set in .env or config/settings.yaml")
    csv_path = Path(csv_path_str)

    settings = PipelineSettings(
        data_source=DataSourceConfig(
            mode=data_source_cfg.get("mode", "csv_mockup"),
            csv_path=csv_path,
        ),
        processing=ProcessingConfig(
            min_samples_per_province=int(cfg.get("processing", {}).get("min_samples_per_province", 300)),
        ),
        storage=StorageConfig(
            schema=cfg.get("storage", {}).get("schema", "public"),
            table=cfg.get("storage", {}).get("table", "flood_risk_events"),
        ),
        paths=PathsConfig(
            output_dir=Path(cfg.get("paths", {}).get("output_dir", "data/output")),
        ),
        database_url=os.getenv("DATABASE_URL", ""),
        start_date=start_date,
        end_date=end_date,
    )

    if settings.data_source.mode != "csv_mockup":
        raise ValueError("Only data_source.mode=csv_mockup is supported in this build.")

    if not settings.data_source.csv_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {settings.data_source.csv_path}")

    if not settings.database_url:
        raise ValueError("Missing DATABASE_URL in environment variables.")

    return settings
