from etl.db import run_sql_file
from etl.dq import new_run_id, quarantine_raw, run_rules
from etl.load_raw import load_all
from etl.text_features import build_review_features
from tests.conftest import FIXTURE_RAW, SQL_DIR


def build_through_staging(engine, weather_dir):
    """Menjalankan tahap 1-3 pada fixture dan mengembalikan (run_id, hasil_raw, hasil_clean)."""
    with engine.begin() as conn:
        run_sql_file(conn, SQL_DIR / "01_schemas.sql")
        run_sql_file(conn, SQL_DIR / "02_dq.sql")
        run_id = new_run_id(conn)
        load_all(conn, FIXTURE_RAW, weather_dir, require_all_states=False)
        raw = run_rules(conn, run_id, "raw")
        quarantine_raw(conn, run_id)
        run_sql_file(conn, SQL_DIR / "10_staging.sql", {"run_id": run_id})
        build_review_features(conn)
        clean = run_rules(conn, run_id, "clean")
    return run_id, raw, clean
