# EDS Customer Intelligence (Olist) Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A replicable prototype (Docker Compose) that loads 3 sources into PostgreSQL, measures data quality, builds a star schema, and serves a 5-page Streamlit dashboard.

**Architecture:** Python package `etl` orchestrates SQL files: raw (COPY of CSV/JSON, all text) -> DQ rules on raw -> staging (typed, quarantined rows excluded, text features) -> dw (star schema) -> DQ rules on staging. Dashboard reads `dw` and `dq`.

**Tech Stack:** Python 3.12, PostgreSQL 16, psycopg2, SQLAlchemy 2, pandas, Streamlit, Plotly, pytest (pgserver for local tests), Docker Compose.

**Spec:** Dokumen Desain Sistem EDS (https://claude.ai/artifact/U6BEbUHda45ZWNnL3qHidb), copied to `docs/`.

## Global Constraints

- Schemas exactly: `raw`, `staging`, `dw`, `quarantine`, `dq`. DB roles: `analyst` (read dw + dq), `steward` (read raw/quarantine/dq), `engineer` (all).
- 16 DQ rules, IDs: U1 U2 U3 C1 C2 C3 C4 K1 K2 K3 K4 V1 V2 V3 V4 V5; severities berat/ringan/info. C4 info = not in score.
- Score = (checked - failed) / checked * 100, per dimension, measured at stage `raw` and stage `clean`.
- Violating rows go to `quarantine.rejected_row`, never deleted. Pipeline is idempotent: running twice gives identical `dw` counts.
- Star schema tables: dim_customer, dim_seller, dim_product, dim_date, dim_state, dim_weather, fact_order_item, fact_review.
- Heavy-rain threshold lives in `config/settings.toml` (default 50 mm/day). Weather JSON committed in `data/external/weather/`.
- One command to run everything: `docker compose up`. Dashboard on port 8501.
- Raw CSVs are not committed (`data/raw/`), README gives Kaggle links and control row counts.

## Review Focus

- Re-running the pipeline twice must not duplicate rows in dw/quarantine (test: counts equal after 2 runs).
- Missing CSV in `data/raw/` -> clear error naming the file and Kaggle link, non-zero exit.
- Empty/NULL review comments must yield sentiment `tanpa_komentar`, not crash text features.
- Orders without delivery date must have NULL delay_days and is_late false-or-null, not error.
- Sellers absent from funnel must be kept with `via_funnel = false`.

---

### Task 1: Scaffold, config, DB init, raw load
Files: `etl/config.py`, `etl/db.py`, `etl/load_raw.py`, `sql/01_schemas.sql`, `tests/conftest.py`, `tests/test_load_raw.py`, tiny fixtures in `tests/fixtures/raw/`.
Interfaces: `config.settings`, `db.get_engine() -> Engine`, `db.run_sql_file(conn, path, params=None)`, `load_raw.load_all(conn, raw_dir, weather_dir) -> dict[str,int]` (rows per raw table).
- [ ] Test: fixtures load, counts equal fixture row counts; missing file raises `MissingInputError`.
- [ ] Implement via `COPY ... FROM STDIN CSV HEADER` into all-text tables.

### Task 2: Data quality engine
Files: `etl/rules.py`, `sql/02_dq.sql`, `etl/dq.py`, `tests/test_dq.py`.
Interfaces: `dq.run_rules(conn, run_id, stage: Literal['raw','clean']) -> list[RuleResult]`, `dq.quarantine_raw(conn, run_id)`.
- [ ] Test: planted violations in fixtures produce exact failed counts per rule; quarantine has the rows with rule id.

### Task 3: Staging and text features
Files: `sql/10_staging.sql`, `etl/text_features.py`, `tests/test_text_features.py`.
Interfaces: `text_features.analyze(text: str | None) -> TextResult(sentiment, topics: set[str])`.
- [ ] Tests: Portuguese examples map to sentiment/topics; None -> `tanpa_komentar`.

### Task 4: Data warehouse
Files: `sql/20_dw.sql`, `etl/fetch_weather.py`, `tests/test_dw.py`.
- [ ] Tests: fact counts, delay_days, via_funnel false for missing sellers, heavy rain flag.

### Task 5: Orchestration and roles
Files: `etl/run.py`, `sql/30_roles.sql`, `tests/test_pipeline.py`.
- [ ] Test: two consecutive runs -> identical dw counts; dq.etl_run has 2 success rows.

### Task 6: Dashboard and simulation
Files: `dashboard/app.py`, `dashboard/queries.py`, `etl/replay.py`.
- [ ] Smoke test queries against fixture DB; app imports without error.

### Task 7: Docker, README, docs, push
Files: `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `README.md`, `.gitignore`, `docs/`.
- [ ] Verify real-data run in local Postgres, record control counts, push to GitHub.
