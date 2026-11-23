import pytest

from dashboard import queries as q
from etl import replay
from etl.run import run
from tests.conftest import FIXTURE_RAW


@pytest.fixture()
def built(engine, weather_dir):
    run(engine, FIXTURE_RAW, weather_dir, require_all_states=False, fetch=False)
    return engine


@pytest.mark.parametrize("name", [
    "kpi", "rating_by_delay", "late_by_state", "rain_effect", "seller_ranking", "funnel_comparison",
    "topics_negative", "sentiment_vs_score", "dq_dimension", "dq_rules", "quarantine_summary",
    "live_feed_summary", "live_feed_recent"])
def test_every_query_runs(built, name):
    df = getattr(q, name)(built)
    assert df is not None


def test_kpi_counts_orders(built):
    assert int(q.kpi(built).iloc[0].pesanan) > 0


def test_dq_dimension_has_raw_and_clean(built):
    assert set(q.dq_dimension(built)["stage"]) == {"raw", "clean"}


def test_replay_inserts_batches_without_duplicates(built):
    replay.reset(built)
    a = replay.next_batch(built, 2)
    b = replay.next_batch(built, 2)
    assert a == 2 and b >= 0
    with built.connect() as c:
        n, d = c.exec_driver_sql("SELECT count(*), count(DISTINCT order_id) FROM dw.live_feed").one()
    assert n == d == a + b
    total = replay.run(built, batch_size=1000, interval=0)
    with built.connect() as c:
        n2 = c.exec_driver_sql("SELECT count(*) FROM dw.live_feed").scalar()
        orders = c.exec_driver_sql("SELECT count(*) FROM dw.v_order").scalar()
    assert n2 == orders and replay.next_batch(built, 5) == 0


def test_app_module_compiles():
    import py_compile
    from pathlib import Path
    py_compile.compile(str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py"), doraise=True)
