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
    "topics_negative", "sentiment_vs_score", "dq_dimension", "dq_rules", "quarantine_summary"])
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
