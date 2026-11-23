from tests.helpers import build_through_staging

STAGING_COUNTS = {
    "customers": 4, "sellers": 3, "products": 3, "geolocation": 4, "orders": 4,
    "order_items": 5, "payments": 4, "reviews": 4, "funnel": 2, "order_transit_rain": 3,
    "review_text_features": 4,
}

# (diperiksa, gagal) pada staging: aturan berat harus 0 gagal, aturan ringan tetap ditandai
CLEAN_EXPECTED = {
    "U1": (8, 0), "U2": (4, 0), "U3": (4, 0), "C1": (4, 0), "C2": (3, 1), "C3": (3, 0),
    "C4": (4, 0), "K1": (4, 1), "K2": (3, 0), "K3": (5, 0), "K4": (7, 1), "V1": (4, 0),
    "V2": (5, 0), "V3": (4, 1), "V4": (4, 0), "V5": (7, 0),
}


def test_staging_row_counts(engine, weather_dir):
    build_through_staging(engine, weather_dir)
    with engine.connect() as conn:
        got = {t: conn.exec_driver_sql(f"SELECT count(*) FROM staging.{t}").scalar() for t in STAGING_COUNTS}
    assert got == STAGING_COUNTS


def test_quarantined_and_orphan_orders_are_excluded(engine, weather_dir):
    build_through_staging(engine, weather_dir)
    with engine.connect() as conn:
        orders = {r[0] for r in conn.exec_driver_sql("SELECT order_id FROM staging.orders")}
        reviews = {r[0] for r in conn.exec_driver_sql("SELECT review_id || '/' || order_id FROM staging.reviews")}
    # o4 (C3), o6 (C1), o7 (K2) dikarantina; o8 gugur karena pelanggannya c5 dikarantina (V5)
    assert orders == {"o1", "o2", "o3", "o5"}
    assert reviews == {"r1/o1", "r2/o2", "r3/o5", "r5/o2"}


def test_clean_stage_rules_hard_rules_pass(engine, weather_dir):
    _, _, clean = build_through_staging(engine, weather_dir)
    assert {r.rule_id: (r.checked, r.failed) for r in clean} == CLEAN_EXPECTED
    assert all(r.failed == 0 for r in clean if r.severity == "berat")


def test_funnel_and_category_translation(engine, weather_dir):
    build_through_staging(engine, weather_dir)
    with engine.connect() as conn:
        funnel = dict(conn.exec_driver_sql("SELECT seller_id, origin FROM staging.funnel").all())
        cats = dict(conn.exec_driver_sql("SELECT product_id, category_en FROM staging.products").all())
    assert funnel == {"s1": "organic_search", "s2": "paid_search"}
    assert cats == {"p1": "health_beauty", "p2": "tidak_diketahui", "p3": "computers_accessories"}


def test_transit_rain_uses_customer_state_between_carrier_and_delivery(engine, weather_dir):
    build_through_staging(engine, weather_dir)
    with engine.connect() as conn:
        rain = {r[0]: float(r[1]) for r in conn.exec_driver_sql(
            "SELECT order_id, max_rain_mm FROM staging.order_transit_rain")}
    assert rain == {"o1": 60.0, "o2": 55.0, "o3": 0.0}  # o5 belum tiba: tidak ada baris
