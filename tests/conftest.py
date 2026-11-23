import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine

FIXTURE_RAW = Path(__file__).parent / "fixtures" / "raw"
SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _weather_json(rain_by_date: dict[str, float]) -> dict:
    day, end = dt.date(2018, 1, 1), dt.date(2018, 3, 31)
    times, rain, temp = [], [], []
    while day <= end:
        iso = day.isoformat()
        times.append(iso)
        rain.append(rain_by_date.get(iso, 0.0))
        temp.append(28.0)
        day += dt.timedelta(days=1)
    return {"daily": {"time": times, "precipitation_sum": rain, "temperature_2m_max": temp}}


@pytest.fixture(scope="session")
def weather_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("weather")
    data = {
        "SP": {"2018-01-03": 60.0, "2018-01-04": 30.0},
        "RJ": {"2018-01-10": 55.0},
        "MG": {},
    }
    for uf, rain in data.items():
        (d / f"{uf}.json").write_text(json.dumps(_weather_json(rain)), encoding="utf-8")
    return d


@pytest.fixture(scope="session")
def pg_uri():
    import pgserver

    pgdata = tempfile.mkdtemp(prefix="pg", dir="/tmp")
    server = pgserver.get_server(pgdata, cleanup_mode="stop")
    yield server.get_uri().replace("postgresql://", "postgresql+psycopg2://", 1)
    server.cleanup()
    shutil.rmtree(pgdata, ignore_errors=True)


@pytest.fixture()
def engine(pg_uri):
    eng = create_engine(pg_uri, future=True)
    with eng.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA IF EXISTS raw, staging, dw, quarantine, dq CASCADE")
    yield eng
    eng.dispose()
