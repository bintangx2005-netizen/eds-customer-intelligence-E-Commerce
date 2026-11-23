CREATE SEQUENCE IF NOT EXISTS dq.run_seq;

CREATE TABLE IF NOT EXISTS dq.etl_run (
    id          bigserial PRIMARY KEY,
    run_id      bigint NOT NULL,
    step        text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    rows_in     bigint,
    rows_out    bigint,
    status      text NOT NULL DEFAULT 'running',
    message     text
);

CREATE TABLE IF NOT EXISTS dq.rule_result (
    id          bigserial PRIMARY KEY,
    run_id      bigint NOT NULL,
    stage       text NOT NULL CHECK (stage IN ('raw', 'clean')),
    rule_id     text NOT NULL,
    dimension   text NOT NULL,
    severity    text NOT NULL,
    description text NOT NULL,
    checked     bigint NOT NULL,
    failed      bigint NOT NULL,
    measured_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quarantine.rejected_row (
    id           bigserial PRIMARY KEY,
    run_id       bigint NOT NULL,
    table_name   text NOT NULL,
    row_id       bigint NOT NULL,
    business_key text,
    rule_id      text NOT NULL,
    severity     text NOT NULL,
    action       text NOT NULL CHECK (action IN ('dikarantina', 'ditandai')),
    payload      jsonb NOT NULL,
    status       text NOT NULL DEFAULT 'baru',
    detected_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rejected_lookup
    ON quarantine.rejected_row (run_id, table_name, row_id);

DROP TABLE IF EXISTS dq.ref_state CASCADE;
CREATE TABLE dq.ref_state AS
SELECT * FROM (VALUES
 ('AC','Acre','Norte'),('AL','Alagoas','Nordeste'),('AP','Amapá','Norte'),
 ('AM','Amazonas','Norte'),('BA','Bahia','Nordeste'),('CE','Ceará','Nordeste'),
 ('DF','Distrito Federal','Centro-Oeste'),('ES','Espírito Santo','Sudeste'),
 ('GO','Goiás','Centro-Oeste'),('MA','Maranhão','Nordeste'),('MT','Mato Grosso','Centro-Oeste'),
 ('MS','Mato Grosso do Sul','Centro-Oeste'),('MG','Minas Gerais','Sudeste'),
 ('PA','Pará','Norte'),('PB','Paraíba','Nordeste'),('PR','Paraná','Sul'),
 ('PE','Pernambuco','Nordeste'),('PI','Piauí','Nordeste'),('RJ','Rio de Janeiro','Sudeste'),
 ('RN','Rio Grande do Norte','Nordeste'),('RS','Rio Grande do Sul','Sul'),
 ('RO','Rondônia','Norte'),('RR','Roraima','Norte'),('SC','Santa Catarina','Sul'),
 ('SP','São Paulo','Sudeste'),('SE','Sergipe','Nordeste'),('TO','Tocantins','Norte')
) AS v(uf, state_name, region);
ALTER TABLE dq.ref_state ADD PRIMARY KEY (uf);

-- Eksekusi terakhir yang berhasil
CREATE OR REPLACE VIEW dq.v_latest_run AS
SELECT max(run_id) AS run_id FROM dq.etl_run WHERE step = 'finish' AND status = 'success';

CREATE OR REPLACE VIEW dq.v_rule_result_latest AS
SELECT r.run_id, r.stage, r.rule_id, r.dimension, r.severity, r.description, r.checked, r.failed,
       round((r.checked - r.failed)::numeric * 100 / NULLIF(r.checked, 0), 2) AS score
FROM dq.rule_result r JOIN dq.v_latest_run l USING (run_id);

CREATE OR REPLACE VIEW dq.v_dimension_score AS
SELECT stage, dimension,
       sum(checked) AS checked, sum(failed) AS failed,
       round((sum(checked) - sum(failed))::numeric * 100 / NULLIF(sum(checked), 0), 2) AS score
FROM dq.v_rule_result_latest
WHERE severity <> 'info'
GROUP BY stage, dimension;

-- Antrean karantina tanpa isi baris, aman dibaca analis
CREATE OR REPLACE VIEW dq.v_quarantine_queue AS
SELECT q.run_id, q.table_name, q.business_key, q.rule_id, q.severity, q.action, q.status, q.detected_at
FROM quarantine.rejected_row q JOIN dq.v_latest_run l USING (run_id);
