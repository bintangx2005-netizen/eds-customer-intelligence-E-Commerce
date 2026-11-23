"""Menjalankan seluruh pipeline: python -m etl.run

Tahap: init -> ensure_weather -> load_raw -> dq_raw -> staging -> dw -> dq_clean -> roles -> finish.
Setiap tahap dicatat di dq.etl_run (waktu, baris masuk/keluar, status). Pipeline idempotent:
dijalankan ulang menghasilkan isi dw yang sama.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from sqlalchemy import Connection, Engine

from . import fetch_weather
from .config import settings
from .db import get_engine, run_sql_file, scalar
from .dq import dimension_scores, new_run_id, quarantine_raw, run_rules
from .load_raw import MissingInputError, check_inputs, load_all
from .text_features import build_review_features


def _log_start(engine: Engine, run_id: int, step: str) -> int:
    with engine.begin() as conn:
        return conn.exec_driver_sql(
            "INSERT INTO dq.etl_run (run_id, step) VALUES (%s, %s) RETURNING id", (run_id, step)
        ).scalar()


def _log_end(engine: Engine, log_id: int, status: str, rows_in=None, rows_out=None, message=None) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE dq.etl_run SET finished_at = now(), status = %s, rows_in = %s, rows_out = %s, "
            "message = %s WHERE id = %s",
            (status, rows_in, rows_out, message, log_id),
        )


def _step(engine: Engine, run_id: int, name: str, fn: Callable[[Connection], tuple[int | None, int | None]]):
    log_id = _log_start(engine, run_id, name)
    try:
        with engine.begin() as conn:
            rows_in, rows_out = fn(conn)
    except Exception as err:
        _log_end(engine, log_id, "failed", message=f"{type(err).__name__}: {err}"[:2000])
        raise
    _log_end(engine, log_id, "success", rows_in, rows_out)


def run(
    engine: Engine | None = None,
    raw_dir: Path | None = None,
    weather_dir: Path | None = None,
    require_all_states: bool = True,
    fetch: bool = True,
) -> int:
    """Menjalankan pipeline dan mengembalikan run_id."""
    engine = engine or get_engine()
    raw_dir, weather_dir = Path(raw_dir or settings.raw_dir), Path(weather_dir or settings.weather_dir)
    sql = settings.sql_dir
    state: dict = {}

    with engine.begin() as conn:
        run_sql_file(conn, sql / "01_schemas.sql")
        run_sql_file(conn, sql / "02_dq.sql")
        run_id = new_run_id(conn)

    def ensure_weather(conn):
        if require_all_states and fetch:
            try:
                fetched = fetch_weather.ensure(weather_dir)
            except OSError as err:
                raise MissingInputError(
                    f"Data cuaca belum ada dan tidak bisa diunduh ({err}). Jalankan "
                    "'python -m etl.fetch_weather' di komputer yang terhubung internet."
                ) from err
            return None, len(fetched)
        return None, 0

    def load(conn):
        check_inputs(raw_dir, weather_dir, require_all_states)
        state["counts"] = load_all(conn, raw_dir, weather_dir, require_all_states)
        return None, sum(state["counts"].values())

    def dq_raw(conn):
        state["raw"] = run_rules(conn, run_id, "raw")
        return len(state["raw"]), sum(quarantine_raw(conn, run_id).values())

    def staging(conn):
        run_sql_file(conn, sql / "10_staging.sql", {"run_id": run_id})
        return None, build_review_features(conn)

    def dw(conn):
        run_sql_file(conn, sql / "20_dw.sql", {"heavy_rain_mm": settings.heavy_rain_mm})
        return None, scalar(conn, "SELECT count(*) FROM dw.fact_order_item")

    def dq_clean(conn):
        state["clean"] = run_rules(conn, run_id, "clean")
        return len(state["clean"]), None

    def roles(conn):
        run_sql_file(conn, sql / "30_roles.sql", {
            "analyst_password": os.environ.get("EDS_ANALYST_PASSWORD", "analyst"),
            "steward_password": os.environ.get("EDS_STEWARD_PASSWORD", "steward"),
            "engineer_password": os.environ.get("EDS_ENGINEER_PASSWORD", "engineer"),
        })
        return None, None

    for name, fn in [("ensure_weather", ensure_weather), ("load_raw", load), ("dq_raw", dq_raw),
                     ("staging", staging), ("dw", dw), ("dq_clean", dq_clean), ("roles", roles)]:
        _step(engine, run_id, name, fn)
    _step(engine, run_id, "finish", lambda conn: (None, None))
    state["run_id"] = run_id
    run.last_summary = state  # dipakai CLI untuk mencetak ringkasan
    return run_id


def _print_summary(run_id: int, summary: dict) -> None:
    print(f"\nPipeline selesai (run_id={run_id}). Baris raw per tabel:")
    for table, n in summary["counts"].items():
        print(f"  {table:28s} {n:>10,}")
    before, after = dimension_scores(summary["raw"]), dimension_scores(summary["clean"])
    print("\nSkor data quality per dimensi (%), sebelum -> sesudah pembersihan:")
    for dim in before:
        print(f"  {dim:14s} {before[dim]:>7} -> {after[dim]}")


def main() -> int:
    try:
        run_id = run()
    except MissingInputError as err:
        print(f"GAGAL: {err}", file=sys.stderr)
        return 1
    _print_summary(run_id, run.last_summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
