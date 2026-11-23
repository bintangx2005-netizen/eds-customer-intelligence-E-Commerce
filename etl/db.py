"""Koneksi database dan penjalan berkas SQL."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from sqlalchemy import Connection, Engine, create_engine

from .config import settings


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or settings.database_url, future=True)


def render_sql(sql: str, params: Mapping[str, object] | None = None) -> str:
    """Mengganti placeholder {{nama}} dengan nilai (hanya angka/teks tepercaya dari konfigurasi)."""
    for key, value in (params or {}).items():
        sql = sql.replace("{{" + key + "}}", str(value))
    return sql


def run_sql(conn: Connection, sql: str, params: Mapping[str, object] | None = None) -> None:
    conn.exec_driver_sql(render_sql(sql, params))


def run_sql_file(conn: Connection, path: Path, params: Mapping[str, object] | None = None) -> None:
    run_sql(conn, Path(path).read_text(encoding="utf-8"), params)


def scalar(conn: Connection, sql: str, params: Mapping[str, object] | None = None):
    return conn.exec_driver_sql(render_sql(sql, params)).scalar()
