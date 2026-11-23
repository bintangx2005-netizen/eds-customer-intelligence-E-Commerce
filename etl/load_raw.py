"""Tahap 1: memuat CSV Olist/Funnel dan JSON cuaca apa adanya ke skema raw (semua kolom teks)."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from sqlalchemy import Connection

from .config import KAGGLE_FUNNEL, KAGGLE_OLIST

# nama tabel raw -> (nama berkas CSV, sumber Kaggle)
RAW_FILES: dict[str, tuple[str, str]] = {
    "customers": ("olist_customers_dataset.csv", KAGGLE_OLIST),
    "geolocation": ("olist_geolocation_dataset.csv", KAGGLE_OLIST),
    "order_items": ("olist_order_items_dataset.csv", KAGGLE_OLIST),
    "order_payments": ("olist_order_payments_dataset.csv", KAGGLE_OLIST),
    "order_reviews": ("olist_order_reviews_dataset.csv", KAGGLE_OLIST),
    "orders": ("olist_orders_dataset.csv", KAGGLE_OLIST),
    "products": ("olist_products_dataset.csv", KAGGLE_OLIST),
    "sellers": ("olist_sellers_dataset.csv", KAGGLE_OLIST),
    "category_translation": ("product_category_name_translation.csv", KAGGLE_OLIST),
    "closed_deals": ("olist_closed_deals_dataset.csv", KAGGLE_FUNNEL),
    "marketing_qualified_leads": ("olist_marketing_qualified_leads_dataset.csv", KAGGLE_FUNNEL),
}

STATES = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


class MissingInputError(RuntimeError):
    """Berkas masukan yang dibutuhkan tidak ditemukan."""


def check_inputs(raw_dir: Path, weather_dir: Path, require_all_states: bool = True) -> None:
    problems: list[str] = []
    for table, (filename, source) in RAW_FILES.items():
        if not (raw_dir / filename).is_file():
            problems.append(f"- {filename} tidak ada di {raw_dir} (unduh dari {source})")
    if require_all_states:
        missing = [uf for uf in STATES if not (weather_dir / f"{uf}.json").is_file()]
        if missing:
            problems.append(
                f"- JSON cuaca belum ada untuk: {', '.join(missing)} di {weather_dir} "
                "(jalankan: python -m etl.fetch_weather)"
            )
    if problems:
        raise MissingInputError("Berkas masukan tidak lengkap:\n" + "\n".join(problems))


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _copy_csv(conn: Connection, table: str, columns: list[str], stream, source_file: str) -> None:
    cols = ", ".join(_qi(c) for c in columns)
    ddl_cols = ", ".join(f"{_qi(c)} text" for c in columns)
    conn.exec_driver_sql(f"DROP TABLE IF EXISTS raw.{table}")
    conn.exec_driver_sql(
        f"CREATE TABLE raw.{table} (_row_id bigserial PRIMARY KEY, {ddl_cols}, "
        f"_source_file text DEFAULT '{source_file}', _loaded_at timestamptz DEFAULT now())"
    )
    with conn.connection.cursor() as cur:
        cur.copy_expert(
            f"COPY raw.{table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true, FORCE_NULL ({cols}))",
            stream,
        )


def _load_csv_file(conn: Connection, table: str, path: Path) -> None:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        columns = next(csv.reader([fh.readline()]))
        fh.seek(0)
        _copy_csv(conn, table, [c.strip() for c in columns], fh, path.name)


def _load_weather(conn: Connection, weather_dir: Path, require_all_states: bool) -> None:
    """JSON Open-Meteo: {"daily": {"time": [...], "precipitation_sum": [...], "temperature_2m_max": [...]}}."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["state_uf", "obs_date", "precipitation_mm", "temp_max_c"])
    files = sorted(weather_dir.glob("*.json"))
    if require_all_states:
        files = [p for p in files if p.stem in STATES]
    for path in files:
        daily = json.loads(path.read_text(encoding="utf-8"))["daily"]
        for day, rain, temp in zip(
            daily["time"], daily["precipitation_sum"], daily["temperature_2m_max"]
        ):
            writer.writerow([path.stem, day, "" if rain is None else rain, "" if temp is None else temp])
    buf.seek(0)
    _copy_csv(conn, "weather_daily", ["state_uf", "obs_date", "precipitation_mm", "temp_max_c"], buf, "open-meteo")


def load_all(
    conn: Connection, raw_dir: Path, weather_dir: Path, require_all_states: bool = True
) -> dict[str, int]:
    """Memuat seluruh sumber ke raw dan mengembalikan jumlah baris per tabel."""
    raw_dir, weather_dir = Path(raw_dir), Path(weather_dir)
    check_inputs(raw_dir, weather_dir, require_all_states)
    for table, (filename, _source) in RAW_FILES.items():
        _load_csv_file(conn, table, raw_dir / filename)
    _load_weather(conn, weather_dir, require_all_states)
    counts: dict[str, int] = {}
    for table in [*RAW_FILES, "weather_daily"]:
        counts[table] = conn.exec_driver_sql(f"SELECT count(*) FROM raw.{table}").scalar()
    return counts
