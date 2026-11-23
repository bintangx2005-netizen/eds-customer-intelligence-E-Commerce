"""Konfigurasi proyek: lokasi berkas, URL database, dan pengaturan dari config/settings.toml."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(os.environ.get("EDS_ROOT", Path(__file__).resolve().parent.parent))

KAGGLE_OLIST = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
KAGGLE_FUNNEL = "https://www.kaggle.com/datasets/olistbr/marketing-funnel-olist"


@dataclass(frozen=True)
class Settings:
    database_url: str
    raw_dir: Path
    weather_dir: Path
    sql_dir: Path
    heavy_rain_mm: float
    weather_start: str
    weather_end: str
    weather_timezone: str
    replay_batch_size: int
    replay_interval_seconds: float


def load_settings() -> Settings:
    with open(ROOT / "config" / "settings.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    weather, replay = cfg["weather"], cfg["replay"]
    return Settings(
        database_url=os.environ.get(
            "EDS_DATABASE_URL", "postgresql+psycopg2://eds:eds@localhost:5432/eds"
        ),
        raw_dir=Path(os.environ.get("EDS_RAW_DIR", ROOT / "data" / "raw")),
        weather_dir=Path(
            os.environ.get("EDS_WEATHER_DIR", ROOT / "data" / "external" / "weather")
        ),
        sql_dir=ROOT / "sql",
        heavy_rain_mm=float(os.environ.get("EDS_HEAVY_RAIN_MM", weather["heavy_rain_mm"])),
        weather_start=weather["start_date"],
        weather_end=weather["end_date"],
        weather_timezone=weather["timezone"],
        replay_batch_size=int(replay["batch_size"]),
        replay_interval_seconds=float(replay["interval_seconds"]),
    )


settings = load_settings()
