from etl.db import run_sql_file
from etl.dq import dimension_scores, new_run_id, quarantine_raw, run_rules
from etl.load_raw import load_all
from tests.conftest import FIXTURE_RAW, SQL_DIR

# (diperiksa, gagal) pada data mentah fixture, dihitung manual dari berkas CSV
RAW_EXPECTED = {
    "U1": (13, 0), "U2": (6, 1), "U3": (7, 1), "C1": (8, 1), "C2": (3, 1), "C3": (6, 1),
    "C4": (6, 1), "K1": (7, 1), "K2": (5, 1), "K3": (10, 1), "K4": (8, 2), "V1": (6, 1),
    "V2": (10, 1), "V3": (4, 1), "V4": (7, 1), "V5": (8, 1),
}


def _prepare(engine, weather_dir):
    with engine.begin() as conn:
        run_sql_file(conn, SQL_DIR / "01_schemas.sql")
        run_sql_file(conn, SQL_DIR / "02_dq.sql")
        load_all(conn, FIXTURE_RAW, weather_dir, require_all_states=False)
        return new_run_id(conn)


def test_raw_rule_counts_match_planted_violations(engine, weather_dir):
    run_id = _prepare(engine, weather_dir)
    with engine.begin() as conn:
        results = run_rules(conn, run_id, "raw")
    assert {r.rule_id: (r.checked, r.failed) for r in results} == RAW_EXPECTED


def test_quarantine_has_rule_ids_and_keeps_rows(engine, weather_dir):
    run_id = _prepare(engine, weather_dir)
    with engine.begin() as conn:
        by_rule = quarantine_raw(conn, run_id)
        orders_left = conn.exec_driver_sql("SELECT count(*) FROM raw.orders").scalar()
        keys = conn.exec_driver_sql(
            "SELECT rule_id, business_key, action FROM quarantine.rejected_row WHERE run_id = %s", (run_id,)
        ).all()
    assert orders_left == 8  # karantina tidak menghapus data mentah
    assert ("C1", "o6", "dikarantina") in keys
    assert ("C3", "o4", "dikarantina") in keys
    assert ("K2", "o7", "dikarantina") in keys
    assert ("K3", "o2/2", "dikarantina") in keys
    assert ("V2", "o3/2", "dikarantina") in keys
    assert ("V1", "r4/o1", "dikarantina") in keys
    assert ("U2", "r3/o3", "dikarantina") in keys
    assert ("V5", "c5", "dikarantina") in keys
    assert ("K1", "o3", "ditandai") in keys
    assert by_rule["V4"] == 1 and by_rule["K4"] == 2 and by_rule["V3"] == 1


def test_dimension_score_excludes_info_rules(engine, weather_dir):
    run_id = _prepare(engine, weather_dir)
    with engine.begin() as conn:
        results = run_rules(conn, run_id, "raw")
    scores = dimension_scores(results)
    # completeness: C1 (8,1) + C2 (3,1) + C3 (6,1) = 17 diperiksa, 3 gagal; C4 (info) diabaikan
    assert scores["completeness"] == round((17 - 3) * 100 / 17, 2)
    assert scores["uniqueness"] == round((26 - 2) * 100 / 26, 2)
