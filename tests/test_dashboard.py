import pytest

from dashboard import queries as q
from etl.run import run
from tests.conftest import FIXTURE_RAW


@pytest.fixture()
def built(engine, weather_dir):
    run(engine, FIXTURE_RAW, weather_dir, require_all_states=False, fetch=False)
    return engine


@pytest.mark.parametrize("name", [
    "kpi", "rating_by_delay", "late_by_state", "rain_effect", "seller_ranking", "funnel_comparison",
    "topics_negative", "sentiment_vs_score", "dq_dimension", "dq_rules", "quarantine_summary",
    "monthly_trend", "bad_review_by_lateness", "seller_concentration"])
def test_every_query_runs(built, name):
    df = getattr(q, name)(built)
    assert df is not None


def test_kpi_counts_orders(built):
    assert int(q.kpi(built).iloc[0].pesanan) > 0


def test_dq_dimension_has_raw_and_clean(built):
    assert set(q.dq_dimension(built)["stage"]) == {"raw", "clean"}


def test_app_module_compiles():
    import py_compile
    from pathlib import Path
    py_compile.compile(str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py"), doraise=True)


def test_insights_build_from_fixture_data(built):
    from dashboard import insights
    items = insights.build(q.kpi(built).iloc[0], q.rating_by_delay(built), q.late_by_state(built),
                           q.topics_negative(built), q.bad_review_by_lateness(built),
                           q.seller_concentration(built), q.rain_effect(built))
    assert isinstance(items, list)
    for it in items:
        assert it["judul"] and it["insight"] and it["rekomendasi"]


def test_insights_handle_empty_inputs():
    import pandas as pd
    from dashboard import insights
    e = pd.DataFrame()
    k = pd.Series({"pct_terlambat": 0.0})
    assert insights.build(k, e, e, e, e, e, e) == []
