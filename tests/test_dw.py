from etl.db import run_sql_file
from tests.conftest import SQL_DIR
from tests.helpers import build_through_staging


def _build(engine, weather_dir, heavy=50.0):
    build_through_staging(engine, weather_dir)
    with engine.begin() as conn:
        run_sql_file(conn, SQL_DIR / "20_dw.sql", {"heavy_rain_mm": heavy})


def _rows(engine, sql):
    with engine.connect() as conn:
        return conn.exec_driver_sql(sql).all()


def test_star_schema_row_counts(engine, weather_dir):
    _build(engine, weather_dir)
    counts = {t: _rows(engine, f"SELECT count(*) FROM dw.{t}")[0][0] for t in [
        "dim_state", "dim_date", "dim_customer", "dim_seller", "dim_product", "dim_weather",
        "fact_order_item", "fact_review"]}
    assert counts == {"dim_state": 27, "dim_date": 1096, "dim_customer": 4, "dim_seller": 3,
                      "dim_product": 3, "dim_weather": 270, "fact_order_item": 5, "fact_review": 4}


def test_delay_days_and_is_late(engine, weather_dir):
    _build(engine, weather_dir)
    got = {r[0]: (r[1], r[2]) for r in _rows(
        engine, "SELECT order_id, delay_days, is_late FROM dw.v_order")}
    assert got == {"o1": (-5, False), "o2": (5, True), "o3": (-8, False), "o5": (None, None)}


def test_rain_in_transit_and_heavy_rain_threshold(engine, weather_dir):
    _build(engine, weather_dir)
    rain = {r[0]: r[1] for r in _rows(engine, "SELECT order_id, max_rain_mm FROM dw.v_order")}
    assert {k: (None if v is None else float(v)) for k, v in rain.items()} == {
        "o1": 60.0, "o2": 55.0, "o3": 0.0, "o5": None}
    assert _rows(engine, "SELECT count(*) FROM dw.dim_weather WHERE is_heavy_rain")[0][0] == 2
    _build(engine, weather_dir, heavy=58.0)  # ambang lebih tinggi: hanya 60 mm yang lebat
    assert _rows(engine, "SELECT count(*) FROM dw.dim_weather WHERE is_heavy_rain")[0][0] == 1


def test_sellers_not_in_funnel_are_kept(engine, weather_dir):
    _build(engine, weather_dir)
    got = {r[0]: r[1] for r in _rows(engine, "SELECT seller_id, via_funnel FROM dw.dim_seller")}
    assert got == {"s1": True, "s2": True, "s3": False}


def test_order_review_and_seller_views(engine, weather_dir):
    _build(engine, weather_dir)
    scores = {r[0]: None if r[1] is None else float(r[1]) for r in _rows(
        engine, "SELECT order_id, avg_score FROM dw.v_order_review")}
    assert scores == {"o1": 5.0, "o2": 1.5, "o3": None, "o5": 3.0}
    perf = {r[0]: (r[1], r[2], r[3]) for r in _rows(
        engine, "SELECT seller_id, n_orders, late_orders, late_rate FROM dw.v_seller_perf")}
    assert perf["s2"][:2] == (2, 1) and float(perf["s2"][2]) == 0.5
    assert perf["s1"][:2] == (2, 0)


def test_review_features_in_fact_review(engine, weather_dir):
    _build(engine, weather_dir)
    got = {r[0]: r[1] for r in _rows(engine, "SELECT review_id, sentiment FROM dw.fact_review")}
    assert got == {"r1": "positif", "r2": "negatif", "r3": "negatif", "r5": "negatif"}
    topics = {r[0] for r in _rows(engine, "SELECT topic FROM dw.v_review_topic WHERE review_id = 'r5'")}
    assert topics == {"layanan", "pengiriman", "kualitas"}
