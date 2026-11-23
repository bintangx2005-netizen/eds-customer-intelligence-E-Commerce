"""Query dashboard. Semua membaca dw/dq lewat peran `analyst` (hanya-baca)."""
from __future__ import annotations

import os

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_URL = "postgresql+psycopg2://analyst:analyst@localhost:5432/eds"


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or os.environ.get("DASHBOARD_DATABASE_URL", DEFAULT_URL), pool_pre_ping=True)


def _df(engine: Engine, sql: str, **params) -> pd.DataFrame:
    with engine.connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def kpi(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT count(*) AS pesanan,
               round(avg(is_late::int) FILTER (WHERE is_late IS NOT NULL) * 100, 2) AS pct_terlambat,
               round(avg(avg_score), 2) AS rata_rating,
               round(sum(item_value), 0) AS nilai_barang
        FROM dw.v_order_review""")


def rating_by_delay(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT CASE WHEN delay_days <= -7 THEN '1. Awal >=7 hari'
                    WHEN delay_days <= 0 THEN '2. Tepat waktu'
                    WHEN delay_days <= 7 THEN '3. Telat 1-7 hari'
                    ELSE '4. Telat >7 hari' END AS kelompok,
               count(*) AS pesanan, round(avg(avg_score), 2) AS rata_rating
        FROM dw.v_order_review
        WHERE delay_days IS NOT NULL AND avg_score IS NOT NULL
        GROUP BY 1 ORDER BY 1""")


def late_by_state(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT s.uf, s.region, count(*) AS pesanan,
               round(avg(o.is_late::int) * 100, 2) AS pct_terlambat
        FROM dw.v_order o JOIN dw.dim_state s USING (state_key)
        WHERE o.is_late IS NOT NULL
        GROUP BY s.uf, s.region ORDER BY pct_terlambat DESC""")


def rain_effect(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT CASE WHEN max_rain_mm IS NULL THEN 'Tidak ada data cuaca'
                    WHEN max_rain_mm >= 50 THEN 'Hujan lebat (>=50 mm)'
                    WHEN max_rain_mm >= 10 THEN 'Hujan sedang (10-50 mm)'
                    ELSE 'Kering/ringan (<10 mm)' END AS kondisi,
               count(*) AS pesanan, round(avg(is_late::int) * 100, 2) AS pct_terlambat
        FROM dw.v_order WHERE is_late IS NOT NULL
        GROUP BY 1 ORDER BY 1""")


def seller_ranking(engine: Engine, min_orders: int = 30, limit: int = 20) -> pd.DataFrame:
    return _df(engine, """
        SELECT seller_id, seller_state, business_segment, via_funnel, n_delivered,
               late_rate, avg_score, revenue
        FROM dw.v_seller_perf
        WHERE n_delivered >= :m ORDER BY late_rate DESC NULLS LAST, n_delivered DESC LIMIT :l""",
               m=min_orders, l=limit)


def funnel_comparison(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT CASE WHEN via_funnel THEN 'Via funnel pemasaran' ELSE 'Non-funnel' END AS asal,
               count(*) AS penjual, round(avg(late_rate) * 100, 2) AS pct_terlambat,
               round(avg(avg_score), 2) AS rata_rating
        FROM dw.v_seller_perf WHERE n_delivered >= 10 GROUP BY via_funnel""")


def topics_negative(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT topic, count(*) AS ulasan FROM dw.v_review_topic
        WHERE score <= 2 GROUP BY topic ORDER BY ulasan DESC""")


def sentiment_vs_score(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT sentiment, count(*) AS ulasan, round(avg(score), 2) AS rata_rating
        FROM dw.fact_review GROUP BY sentiment ORDER BY sentiment""")


def dq_dimension(engine: Engine) -> pd.DataFrame:
    return _df(engine, "SELECT stage, dimension, checked, failed, score FROM dq.v_dimension_score")


def dq_rules(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT rule_id, dimension, severity, description, stage, checked, failed, score
        FROM dq.v_rule_result_latest ORDER BY rule_id, stage""")


def quarantine_summary(engine: Engine) -> pd.DataFrame:
    return _df(engine, """
        SELECT rule_id, severity, action, status, count(*) AS baris
        FROM dq.v_quarantine_queue GROUP BY 1, 2, 3, 4 ORDER BY baris DESC""")
