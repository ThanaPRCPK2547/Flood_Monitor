from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from flood_pipeline.pipeline import run_pipeline


if __name__ == "__main__":
    config_path = os.getenv("FLOOD_CONFIG_PATH", "config/settings.yaml")
    summary = run_pipeline(config_path=config_path)
    print(json.dumps(summary, indent=2))
