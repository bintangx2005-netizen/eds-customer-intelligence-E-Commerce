import shutil

import pytest
from sqlalchemy.exc import DBAPIError

from etl.load_raw import MissingInputError
from etl.run import run
from tests.conftest import FIXTURE_RAW

DW_TABLES = ["dim_state", "dim_date", "dim_customer", "dim_seller", "dim_product", "dim_weather",
             "fact_order_item", "fact_review"]


def _run(engine, weather_dir, raw_dir=FIXTURE_RAW):
    return run(engine, raw_dir, weather_dir, require_all_states=False, fetch=False)


def _dw_counts(engine):
    with engine.connect() as conn:
        return {t: conn.exec_driver_sql(f"SELECT count(*) FROM dw.{t}").scalar() for t in DW_TABLES}


def test_running_twice_gives_identical_dw_and_logs_both_runs(engine, weather_dir):
    first = _run(engine, weather_dir)
    counts1 = _dw_counts(engine)
    second = _run(engine, weather_dir)
    assert second > first and _dw_counts(engine) == counts1
    with engine.connect() as conn:
        finished = conn.exec_driver_sql(
            "SELECT count(DISTINCT run_id) FROM dq.etl_run WHERE step = 'finish' AND status = 'success'"
        ).scalar()
        steps = [r[0] for r in conn.exec_driver_sql(
            "SELECT step FROM dq.etl_run WHERE run_id = %s ORDER BY id", (second,))]
        queue = conn.exec_driver_sql("SELECT count(DISTINCT run_id) FROM dq.v_quarantine_queue").scalar()
    assert finished == 2 and queue == 1
    assert steps == ["ensure_weather", "load_raw", "dq_raw", "staging", "dw", "dq_clean", "roles", "finish"]


def test_dimension_scores_improve_after_cleaning(engine, weather_dir):
    _run(engine, weather_dir)
    with engine.connect() as conn:
        rows = {(s, d): float(v) for s, d, v in conn.exec_driver_sql(
            "SELECT stage, dimension, score FROM dq.v_dimension_score")}
    for dim in ("uniqueness", "completeness", "consistency", "validity"):
        assert rows[("clean", dim)] >= rows[("raw", dim)]
    assert rows[("clean", "uniqueness")] == 100.0


def test_failed_step_is_logged_and_error_names_missing_file(engine, weather_dir, tmp_path):
    for f in FIXTURE_RAW.iterdir():
        if f.name != "olist_orders_dataset.csv":
            shutil.copy(f, tmp_path / f.name)
    with pytest.raises(MissingInputError, match="olist_orders_dataset.csv"):
        _run(engine, weather_dir, raw_dir=tmp_path)
    with engine.connect() as conn:
        status, message = conn.exec_driver_sql(
            "SELECT status, message FROM dq.etl_run WHERE step = 'load_raw'").one()
    assert status == "failed" and "olist_orders_dataset.csv" in message


def test_database_roles_enforce_governance(engine, weather_dir):
    _run(engine, weather_dir)

    def attempt(role, sql):
        with engine.connect() as conn:
            conn.exec_driver_sql(f"SET ROLE {role}")
            try:
                return conn.exec_driver_sql(sql).all()
            finally:
                conn.rollback()

    assert attempt("analyst", "SELECT count(*) FROM dw.fact_review") == [(4,)]
    assert attempt("analyst", "SELECT count(*) FROM dq.v_dimension_score")[0][0] > 0
    for forbidden in ("SELECT 1 FROM raw.orders", "SELECT 1 FROM quarantine.rejected_row",
                      "SELECT 1 FROM dq.rule_result"):
        with pytest.raises(DBAPIError, match="permission denied"):
            attempt("analyst", forbidden)
    assert attempt("steward", "SELECT count(*) FROM raw.orders") == [(8,)]
    assert attempt("steward", "SELECT count(*) FROM quarantine.rejected_row")[0][0] > 0
    with pytest.raises(DBAPIError, match="permission denied"):
        attempt("steward", "SELECT 1 FROM dw.fact_review")
    assert attempt("engineer", "SELECT count(*) FROM staging.orders") == [(4,)]
