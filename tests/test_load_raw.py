import shutil

import pytest

from etl.db import run_sql_file
from etl.load_raw import MissingInputError, load_all
from tests.conftest import FIXTURE_RAW, SQL_DIR

EXPECTED = {
    "customers": 5, "geolocation": 7, "order_items": 10, "order_payments": 4,
    "order_reviews": 6, "orders": 8, "products": 3, "sellers": 3,
    "category_translation": 2, "closed_deals": 2, "marketing_qualified_leads": 3,
    "weather_daily": 270,
}


def _load(engine, weather_dir, raw_dir=FIXTURE_RAW):
    with engine.begin() as conn:
        run_sql_file(conn, SQL_DIR / "01_schemas.sql")
        return load_all(conn, raw_dir, weather_dir, require_all_states=False)


def test_row_counts_match_fixture_files(engine, weather_dir):
    assert _load(engine, weather_dir) == EXPECTED


def test_multiline_comment_and_accents_are_preserved(engine, weather_dir):
    _load(engine, weather_dir)
    with engine.connect() as conn:
        msg = conn.exec_driver_sql(
            "SELECT review_comment_message FROM raw.order_reviews WHERE review_id='r5'"
        ).scalar()
        first = conn.exec_driver_sql(
            "SELECT review_comment_message FROM raw.order_reviews WHERE review_id='r1'"
        ).scalar()
    assert msg == "Vendedor não responde.\nEntrega atrasou e veio quebrado"
    assert first.startswith("Ótimo produto")


def test_empty_comment_becomes_null(engine, weather_dir):
    _load(engine, weather_dir)
    with engine.connect() as conn:
        n = conn.exec_driver_sql(
            "SELECT count(*) FROM raw.order_reviews WHERE review_comment_message IS NULL"
        ).scalar()
    assert n == 1


def test_missing_csv_names_file_and_source(engine, weather_dir, tmp_path):
    for f in FIXTURE_RAW.iterdir():
        if f.name != "olist_orders_dataset.csv":
            shutil.copy(f, tmp_path / f.name)
    with pytest.raises(MissingInputError) as err:
        _load(engine, weather_dir, raw_dir=tmp_path)
    assert "olist_orders_dataset.csv" in str(err.value)
    assert "kaggle.com" in str(err.value)
