-- Tahap 3: staging bertipe. Baris yang dikarantina (aturan berat) tidak ikut; aturan ringan hanya menandai.
-- {{run_id}} diganti oleh pipeline.

CREATE TABLE staging.customers AS
SELECT c.customer_id, c.customer_unique_id, c.customer_zip_code_prefix AS zip_prefix,
       c.customer_city AS city, c.customer_state AS state
FROM raw.customers c
WHERE NOT EXISTS (SELECT 1 FROM quarantine.rejected_row q
                  WHERE q.run_id = {{run_id}} AND q.action = 'dikarantina'
                    AND q.table_name = 'customers' AND q.row_id = c._row_id);
ALTER TABLE staging.customers ADD PRIMARY KEY (customer_id);

CREATE TABLE staging.sellers AS
SELECT s.seller_id, s.seller_zip_code_prefix AS zip_prefix, s.seller_city AS city, s.seller_state AS state
FROM raw.sellers s
WHERE NOT EXISTS (SELECT 1 FROM quarantine.rejected_row q
                  WHERE q.run_id = {{run_id}} AND q.action = 'dikarantina'
                    AND q.table_name = 'sellers' AND q.row_id = s._row_id);
ALTER TABLE staging.sellers ADD PRIMARY KEY (seller_id);

CREATE TABLE staging.products AS
SELECT p.product_id,
       NULLIF(trim(p.product_category_name), '') AS category_pt,
       COALESCE(t.product_category_name_english,
                CASE WHEN NULLIF(trim(p.product_category_name), '') IS NULL THEN 'tidak_diketahui'
                     ELSE p.product_category_name END) AS category_en,
       NULLIF(p.product_weight_g, '')::numeric AS weight_g
FROM raw.products p
LEFT JOIN raw.category_translation t ON t.product_category_name = p.product_category_name;
ALTER TABLE staging.products ADD PRIMARY KEY (product_id);

-- Satu titik per kode pos (median koordinat, kuat terhadap koordinat pencilan)
CREATE TABLE staging.geolocation AS
SELECT geolocation_zip_code_prefix AS zip_prefix,
       (percentile_cont(0.5) WITHIN GROUP (ORDER BY NULLIF(geolocation_lat, '')::numeric))::numeric(9,6) AS lat,
       (percentile_cont(0.5) WITHIN GROUP (ORDER BY NULLIF(geolocation_lng, '')::numeric))::numeric(9,6) AS lng,
       mode() WITHIN GROUP (ORDER BY geolocation_city) AS city,
       mode() WITHIN GROUP (ORDER BY geolocation_state) AS state
FROM raw.geolocation
GROUP BY geolocation_zip_code_prefix;
ALTER TABLE staging.geolocation ADD PRIMARY KEY (zip_prefix);

-- Item yang lolos aturan dan punya penjual serta produk di staging
CREATE TABLE staging._item_ok AS
SELECT i._row_id
FROM raw.order_items i
WHERE NOT EXISTS (SELECT 1 FROM quarantine.rejected_row q
                  WHERE q.run_id = {{run_id}} AND q.action = 'dikarantina'
                    AND q.table_name = 'order_items' AND q.row_id = i._row_id)
  AND EXISTS (SELECT 1 FROM staging.sellers s WHERE s.seller_id = i.seller_id)
  AND EXISTS (SELECT 1 FROM staging.products p WHERE p.product_id = i.product_id);
ALTER TABLE staging._item_ok ADD PRIMARY KEY (_row_id);

CREATE TABLE staging.orders AS
SELECT o.order_id, o.customer_id, o.order_status AS status,
       NULLIF(o.order_purchase_timestamp, '')::timestamp AS purchase_ts,
       NULLIF(o.order_approved_at, '')::timestamp AS approved_ts,
       NULLIF(o.order_delivered_carrier_date, '')::timestamp AS carrier_ts,
       NULLIF(o.order_delivered_customer_date, '')::timestamp AS delivered_ts,
       NULLIF(o.order_estimated_delivery_date, '')::timestamp AS estimated_ts
FROM raw.orders o
WHERE NOT EXISTS (SELECT 1 FROM quarantine.rejected_row q
                  WHERE q.run_id = {{run_id}} AND q.action = 'dikarantina'
                    AND q.table_name = 'orders' AND q.row_id = o._row_id)
  AND EXISTS (SELECT 1 FROM staging.customers c WHERE c.customer_id = o.customer_id)
  AND EXISTS (SELECT 1 FROM raw.order_items i JOIN staging._item_ok k ON k._row_id = i._row_id
              WHERE i.order_id = o.order_id);
ALTER TABLE staging.orders ADD PRIMARY KEY (order_id);

CREATE TABLE staging.order_items AS
SELECT i.order_id, i.order_item_id::int AS order_item_id, i.product_id, i.seller_id,
       NULLIF(i.shipping_limit_date, '')::timestamp AS shipping_limit_ts,
       NULLIF(i.price, '')::numeric AS price, NULLIF(i.freight_value, '')::numeric AS freight_value
FROM raw.order_items i
JOIN staging._item_ok k ON k._row_id = i._row_id
JOIN staging.orders o ON o.order_id = i.order_id;
CREATE INDEX ix_stg_items_order ON staging.order_items (order_id);
DROP TABLE staging._item_ok;

CREATE TABLE staging.payments AS
SELECT p.order_id, p.payment_sequential::int AS seq, p.payment_type AS type,
       p.payment_installments::int AS installments, NULLIF(p.payment_value, '')::numeric AS value
FROM raw.order_payments p
WHERE EXISTS (SELECT 1 FROM staging.orders o WHERE o.order_id = p.order_id);
CREATE INDEX ix_stg_payments_order ON staging.payments (order_id);

CREATE TABLE staging.reviews AS
SELECT r.review_id, r.order_id, r.review_score::int AS score,
       NULLIF(trim(r.review_comment_title), '') AS title,
       NULLIF(trim(r.review_comment_message), '') AS comment,
       NULLIF(r.review_creation_date, '')::timestamp AS creation_ts,
       NULLIF(r.review_answer_timestamp, '')::timestamp AS answer_ts
FROM raw.order_reviews r
WHERE NOT EXISTS (SELECT 1 FROM quarantine.rejected_row q
                  WHERE q.run_id = {{run_id}} AND q.action = 'dikarantina'
                    AND q.table_name = 'order_reviews' AND q.row_id = r._row_id)
  AND EXISTS (SELECT 1 FROM staging.orders o WHERE o.order_id = r.order_id);
ALTER TABLE staging.reviews ADD PRIMARY KEY (review_id);
CREATE INDEX ix_stg_reviews_order ON staging.reviews (order_id);

-- Penjual dari Marketing Funnel: satu baris per penjual (kesepakatan paling awal)
CREATE TABLE staging.funnel AS
SELECT DISTINCT ON (d.seller_id) d.seller_id, d.mql_id, d.business_segment, d.lead_type, m.origin,
       NULLIF(d.won_date, '')::timestamp AS won_ts
FROM raw.closed_deals d
LEFT JOIN raw.marketing_qualified_leads m ON m.mql_id = d.mql_id
ORDER BY d.seller_id, NULLIF(d.won_date, '')::timestamp;
ALTER TABLE staging.funnel ADD PRIMARY KEY (seller_id);

CREATE TABLE staging.weather AS
SELECT state_uf AS uf, obs_date::date AS obs_date,
       NULLIF(precipitation_mm, '')::numeric AS precipitation_mm,
       NULLIF(temp_max_c, '')::numeric AS temp_max_c
FROM raw.weather_daily;
CREATE INDEX ix_stg_weather ON staging.weather (uf, obs_date);

-- Curah hujan maksimum di negara bagian pelanggan antara serah ke kurir dan tiba
CREATE TABLE staging.order_transit_rain AS
SELECT o.order_id, max(w.precipitation_mm) AS max_rain_mm
FROM staging.orders o
JOIN staging.customers c ON c.customer_id = o.customer_id
JOIN staging.weather w ON w.uf = c.state
     AND w.obs_date BETWEEN o.carrier_ts::date AND o.delivered_ts::date
WHERE o.carrier_ts IS NOT NULL AND o.delivered_ts IS NOT NULL
GROUP BY o.order_id;
ALTER TABLE staging.order_transit_rain ADD PRIMARY KEY (order_id);
