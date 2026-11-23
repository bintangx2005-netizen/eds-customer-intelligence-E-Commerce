-- Tata kelola di dalam database: tiga peran dengan hak akses berbeda (bagian 7 dokumen desain).
-- Kata sandi di bawah hanya untuk demo; ubah lewat variabel lingkungan EDS_*_PASSWORD.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN CREATE ROLE analyst LOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'steward') THEN CREATE ROLE steward LOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'engineer') THEN CREATE ROLE engineer LOGIN; END IF;
END $$;
ALTER ROLE analyst PASSWORD '{{analyst_password}}';
ALTER ROLE steward PASSWORD '{{steward_password}}';
ALTER ROLE engineer PASSWORD '{{engineer_password}}';

REVOKE ALL ON SCHEMA raw, staging, dw, quarantine, dq FROM analyst, steward, engineer;

-- analyst: hanya membaca dw dan tampilan hasil kualitas
GRANT USAGE ON SCHEMA dw, dq TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA dw TO analyst;
GRANT SELECT ON dq.v_latest_run, dq.v_rule_result_latest, dq.v_dimension_score,
                dq.v_quarantine_queue TO analyst;

-- steward: membaca raw, quarantine, dq dan memutuskan status baris karantina
GRANT USAGE ON SCHEMA raw, quarantine, dq TO steward;
GRANT SELECT ON ALL TABLES IN SCHEMA raw, quarantine, dq TO steward;
GRANT UPDATE (status) ON quarantine.rejected_row TO steward;

-- engineer: akses penuh pada seluruh skema
GRANT ALL ON SCHEMA raw, staging, dw, quarantine, dq TO engineer;
GRANT ALL ON ALL TABLES IN SCHEMA raw, staging, dw, quarantine, dq TO engineer;
GRANT ALL ON ALL SEQUENCES IN SCHEMA raw, staging, dw, quarantine, dq TO engineer;
