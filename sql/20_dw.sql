-- Tahap 4: skema bintang di dw. {{heavy_rain_mm}} berasal dari config/settings.toml.
-- Seluruh berkas ini berjalan dalam satu transaksi: dw lama baru diganti bila pembangunan berhasil.
DROP SCHEMA IF EXISTS dw CASCADE;
CREATE SCHEMA dw;

CREATE TABLE dw.dim_state AS
SELECT (row_number() OVER (ORDER BY uf))::int AS state_key, uf, state_name, region FROM dq.ref_state;
ALTER TABLE dw.dim_state ADD PRIMARY KEY (state_key);
CREATE UNIQUE INDEX ux_dim_state_uf ON dw.dim_state (uf);

CREATE TABLE dw.dim_date AS
SELECT to_char(d, 'YYYYMMDD')::int AS date_key, d::date AS date,
       extract(year FROM d)::int AS year, extract(month FROM d)::int AS month,
       extract(isodow FROM d)::int AS day_of_week
FROM generate_series('2016-01-01'::date, '2018-12-31'::date, interval '1 day') AS d;
ALTER TABLE dw.dim_date ADD PRIMARY KEY (date_key);

CREATE TABLE dw.dim_customer AS
SELECT (row_number() OVER (ORDER BY c.customer_id))::int AS customer_key,
       c.customer_id, c.customer_unique_id, c.zip_prefix, s.state_key
FROM staging.customers c JOIN dw.dim_state s ON s.uf = c.state;
ALTER TABLE dw.dim_customer ADD PRIMARY KEY (customer_key);
CREATE UNIQUE INDEX ux_dim_customer_id ON dw.dim_customer (customer_id);

CREATE TABLE dw.dim_seller AS
SELECT (row_number() OVER (ORDER BY s.seller_id))::int AS seller_key,
       s.seller_id, s.zip_prefix, st.state_key,
       (f.seller_id IS NOT NULL) AS via_funnel,
       f.business_segment, f.lead_type, f.origin AS lead_origin
FROM staging.sellers s
JOIN dw.dim_state st ON st.uf = s.state
LEFT JOIN staging.funnel f ON f.seller_id = s.seller_id;
ALTER TABLE dw.dim_seller ADD PRIMARY KEY (seller_key);
CREATE UNIQUE INDEX ux_dim_seller_id ON dw.dim_seller (seller_id);

CREATE TABLE dw.dim_product AS
SELECT (row_number() OVER (ORDER BY product_id))::int AS product_key,
       product_id, category_pt, category_en, weight_g
FROM staging.products;
ALTER TABLE dw.dim_product ADD PRIMARY KEY (product_key);
CREATE UNIQUE INDEX ux_dim_product_id ON dw.dim_product (product_id);

CREATE TABLE dw.dim_weather AS
SELECT st.state_key, d.date_key, w.precipitation_mm, w.temp_max_c,
       COALESCE(w.precipitation_mm >= {{heavy_rain_mm}}, false) AS is_heavy_rain
FROM staging.weather w
JOIN dw.dim_state st ON st.uf = w.uf
JOIN dw.dim_date d ON d.date = w.obs_date;
ALTER TABLE dw.dim_weather ADD PRIMARY KEY (state_key, date_key);

CREATE TABLE dw.fact_order_item AS
SELECT i.order_id, i.order_item_id,
       c.customer_key, s.seller_key, p.product_key,
       to_char(o.purchase_ts, 'YYYYMMDD')::int AS purchase_date_key,
       to_char(o.delivered_ts, 'YYYYMMDD')::int AS delivered_date_key,
       c.state_key,
       i.price, i.freight_value,
       (o.delivered_ts::date - o.estimated_ts::date) AS delay_days,
       ((o.delivered_ts::date - o.estimated_ts::date) > 0) AS is_late,
       r.max_rain_mm AS max_rain_in_transit_mm,
       o.status AS order_status
FROM staging.order_items i
JOIN staging.orders o ON o.order_id = i.order_id
JOIN dw.dim_customer c ON c.customer_id = o.customer_id
JOIN dw.dim_seller s ON s.seller_id = i.seller_id
JOIN dw.dim_product p ON p.product_id = i.product_id
LEFT JOIN staging.order_transit_rain r ON r.order_id = o.order_id;
ALTER TABLE dw.fact_order_item ADD PRIMARY KEY (order_id, order_item_id);
CREATE INDEX ix_fact_item_seller ON dw.fact_order_item (seller_key);
CREATE INDEX ix_fact_item_state ON dw.fact_order_item (state_key);

CREATE TABLE dw.fact_review AS
SELECT r.review_id, r.order_id, r.creation_ts::date AS review_date, r.score,
       f.sentiment, f.topik_pengiriman, f.topik_kualitas, f.topik_tidak_sesuai,
       f.topik_layanan, f.topik_kemasan,
       (r.comment IS NOT NULL) AS ada_komentar, r.comment
FROM staging.reviews r
JOIN staging.review_text_features f ON f.review_id = r.review_id;
ALTER TABLE dw.fact_review ADD PRIMARY KEY (review_id);
CREATE INDEX ix_fact_review_order ON dw.fact_review (order_id);

-- Tampilan tingkat pesanan: satu baris per pesanan
CREATE VIEW dw.v_order AS
SELECT f.order_id, max(f.state_key) AS state_key, max(f.purchase_date_key) AS purchase_date_key,
       max(f.delay_days) AS delay_days, bool_or(f.is_late) AS is_late,
       max(f.max_rain_in_transit_mm) AS max_rain_mm, sum(f.price) AS item_value,
       sum(f.freight_value) AS freight_value, count(*) AS n_items, max(f.order_status) AS order_status
FROM dw.fact_order_item f GROUP BY f.order_id;

CREATE VIEW dw.v_order_review AS
SELECT o.*, r.avg_score, r.n_reviews
FROM dw.v_order o
LEFT JOIN (SELECT order_id, avg(score)::numeric(4,2) AS avg_score, count(*) AS n_reviews
           FROM dw.fact_review GROUP BY order_id) r USING (order_id);

-- Kinerja penjual. Ulasan melekat pada pesanan, jadi pesanan multi-penjual berbagi skor yang sama.
CREATE VIEW dw.v_seller_perf AS
WITH so AS (
    SELECT seller_key, order_id, bool_or(is_late) AS is_late, sum(price) AS revenue
    FROM dw.fact_order_item GROUP BY seller_key, order_id
), rv AS (
    SELECT order_id, avg(score) AS avg_score FROM dw.fact_review GROUP BY order_id
)
SELECT s.seller_key, s.seller_id, s.via_funnel, s.business_segment, st.uf AS seller_state,
       count(*) AS n_orders,
       count(*) FILTER (WHERE so.is_late IS NOT NULL) AS n_delivered,
       count(*) FILTER (WHERE so.is_late) AS late_orders,
       round((count(*) FILTER (WHERE so.is_late))::numeric
             / NULLIF(count(*) FILTER (WHERE so.is_late IS NOT NULL), 0), 4) AS late_rate,
       round(avg(rv.avg_score)::numeric, 2) AS avg_score,
       sum(so.revenue) AS revenue
FROM so
JOIN dw.dim_seller s USING (seller_key)
JOIN dw.dim_state st ON st.state_key = s.state_key
LEFT JOIN rv USING (order_id)
GROUP BY s.seller_key, s.seller_id, s.via_funnel, s.business_segment, st.uf;

-- Ulasan per topik keluhan
CREATE VIEW dw.v_review_topic AS
SELECT review_id, score, sentiment, 'pengiriman' AS topic FROM dw.fact_review WHERE topik_pengiriman
UNION ALL SELECT review_id, score, sentiment, 'kualitas' FROM dw.fact_review WHERE topik_kualitas
UNION ALL SELECT review_id, score, sentiment, 'tidak_sesuai' FROM dw.fact_review WHERE topik_tidak_sesuai
UNION ALL SELECT review_id, score, sentiment, 'layanan' FROM dw.fact_review WHERE topik_layanan
UNION ALL SELECT review_id, score, sentiment, 'kemasan' FROM dw.fact_review WHERE topik_kemasan;
