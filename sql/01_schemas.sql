-- Lapisan yang dibangun ulang tiap eksekusi
DROP SCHEMA IF EXISTS raw CASCADE;
DROP SCHEMA IF EXISTS staging CASCADE;
CREATE SCHEMA raw;
CREATE SCHEMA staging;
-- Lapisan yang menyimpan riwayat antar eksekusi
CREATE SCHEMA IF NOT EXISTS quarantine;
CREATE SCHEMA IF NOT EXISTS dq;
