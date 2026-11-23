"""Definisi 16 aturan data quality (bagian 6 dokumen desain).

Setiap aturan punya dua versi SQL: `raw` (menguji skema raw, semua kolom teks) dan `clean`
(menguji skema staging yang sudah bertipe). Aturan berat memindahkan baris ke karantina
(action 'dikarantina'); aturan ringan hanya menandai (action 'ditandai').
"""
from __future__ import annotations

from dataclasses import dataclass

UNIQUENESS, COMPLETENESS, CONSISTENCY, VALIDITY = "uniqueness", "completeness", "consistency", "validity"
BERAT, RINGAN, INFO = "berat", "ringan", "info"


@dataclass(frozen=True)
class Rule:
    id: str
    dimension: str
    severity: str
    description: str
    raw_checked: str
    raw_failed: str
    clean_checked: str
    clean_failed: str
    quarantine: tuple[str, ...] = ()


def _ts(col: str) -> str:
    return f"NULLIF({col}, '')::timestamp"


def _q(table: str, key: str, rule: str, severity: str, where: str, source: str | None = None) -> str:
    action = "dikarantina" if severity == BERAT else "ditandai"
    src = source or f"raw.{table} x"
    return (
        "INSERT INTO quarantine.rejected_row "
        "(run_id, table_name, row_id, business_key, rule_id, severity, action, payload) "
        f"SELECT {{{{run_id}}}}, '{table}', x._row_id, {key}, '{rule}', '{severity}', '{action}', "
        f"to_jsonb(x) - 'rn' FROM {src} WHERE {where}"
    )


def _dups(table: str, partition: str, order: str = "_row_id") -> str:
    return (
        f"(SELECT t.*, row_number() OVER (PARTITION BY {partition} ORDER BY {order}) AS rn "
        f"FROM raw.{table} t) x"
    )


def _count(table: str) -> str:
    return f"SELECT count(*) FROM {table}"


RULES: tuple[Rule, ...] = (
    Rule(
        "U1", UNIQUENESS, BERAT, "order_id dan customer_id tidak duplikat",
        "SELECT (SELECT count(*) FROM raw.orders) + (SELECT count(*) FROM raw.customers)",
        "SELECT (SELECT count(*) - count(DISTINCT order_id) FROM raw.orders) "
        "+ (SELECT count(*) - count(DISTINCT customer_id) FROM raw.customers)",
        "SELECT (SELECT count(*) FROM staging.orders) + (SELECT count(*) FROM staging.customers)",
        "SELECT (SELECT count(*) - count(DISTINCT order_id) FROM staging.orders) "
        "+ (SELECT count(*) - count(DISTINCT customer_id) FROM staging.customers)",
        (
            _q("orders", "x.order_id", "U1", BERAT, "x.rn > 1", _dups("orders", "order_id")),
            _q("customers", "x.customer_id", "U1", BERAT, "x.rn > 1", _dups("customers", "customer_id")),
        ),
    ),
    Rule(
        "U2", UNIQUENESS, BERAT, "review_id tidak duplikat",
        _count("raw.order_reviews"),
        "SELECT count(*) - count(DISTINCT review_id) FROM raw.order_reviews",
        _count("staging.reviews"),
        "SELECT count(*) - count(DISTINCT review_id) FROM staging.reviews",
        (
            _q(
                "order_reviews", "x.review_id || '/' || x.order_id", "U2", BERAT, "x.rn > 1",
                _dups(
                    "order_reviews", "review_id",
                    f"{_ts('review_answer_timestamp')} DESC NULLS LAST, order_id, _row_id",
                ),
            ),
        ),
    ),
    Rule(
        "U3", UNIQUENESS, RINGAN, "baris geolokasi tidak identik dengan baris lain",
        _count("raw.geolocation"),
        "SELECT count(*) - count(DISTINCT (geolocation_zip_code_prefix, geolocation_lat, "
        "geolocation_lng, geolocation_city, geolocation_state)) FROM raw.geolocation",
        _count("staging.geolocation"),
        "SELECT count(*) - count(DISTINCT zip_prefix) FROM staging.geolocation",
        # Duplikat geolokasi diringkas menjadi satu titik per kode pos, bukan dicatat satu per satu.
    ),
    Rule(
        "C1", COMPLETENESS, BERAT, "setiap pesanan memiliki minimal satu item",
        _count("raw.orders"),
        "SELECT count(*) FROM raw.orders o WHERE NOT EXISTS "
        "(SELECT 1 FROM raw.order_items i WHERE i.order_id = o.order_id)",
        _count("staging.orders"),
        "SELECT count(*) FROM staging.orders o WHERE NOT EXISTS "
        "(SELECT 1 FROM staging.order_items i WHERE i.order_id = o.order_id)",
        (
            _q(
                "orders", "x.order_id", "C1", BERAT,
                "NOT EXISTS (SELECT 1 FROM raw.order_items i WHERE i.order_id = x.order_id)",
            ),
        ),
    ),
    Rule(
        "C2", COMPLETENESS, RINGAN, "kategori produk terisi",
        _count("raw.products"),
        "SELECT count(*) FROM raw.products WHERE NULLIF(trim(product_category_name), '') IS NULL",
        _count("staging.products"),
        "SELECT count(*) FROM staging.products WHERE category_pt IS NULL",
        (_q("products", "x.product_id", "C2", RINGAN, "NULLIF(trim(x.product_category_name), '') IS NULL"),),
    ),
    Rule(
        "C3", COMPLETENESS, BERAT, "pesanan berstatus delivered memiliki tanggal tiba",
        "SELECT count(*) FROM raw.orders WHERE order_status = 'delivered'",
        "SELECT count(*) FROM raw.orders WHERE order_status = 'delivered' "
        "AND NULLIF(order_delivered_customer_date, '') IS NULL",
        "SELECT count(*) FROM staging.orders WHERE status = 'delivered'",
        "SELECT count(*) FROM staging.orders WHERE status = 'delivered' AND delivered_ts IS NULL",
        (
            _q(
                "orders", "x.order_id", "C3", BERAT,
                "x.order_status = 'delivered' AND NULLIF(x.order_delivered_customer_date, '') IS NULL",
            ),
        ),
    ),
    Rule(
        "C4", COMPLETENESS, INFO, "komentar ulasan terisi (opsional di sumber, tidak masuk skor)",
        _count("raw.order_reviews"),
        "SELECT count(*) FROM raw.order_reviews WHERE NULLIF(trim(review_comment_message), '') IS NULL",
        _count("staging.reviews"),
        "SELECT count(*) FROM staging.reviews WHERE NULLIF(trim(comment), '') IS NULL",
    ),
    Rule(
        "K1", CONSISTENCY, RINGAN, "tanggal serah ke kurir tidak lebih awal dari tanggal persetujuan",
        "SELECT count(*) FROM raw.orders WHERE NULLIF(order_approved_at, '') IS NOT NULL "
        "AND NULLIF(order_delivered_carrier_date, '') IS NOT NULL",
        "SELECT count(*) FROM raw.orders WHERE "
        f"{_ts('order_delivered_carrier_date')} < {_ts('order_approved_at')}",
        "SELECT count(*) FROM staging.orders WHERE approved_ts IS NOT NULL AND carrier_ts IS NOT NULL",
        "SELECT count(*) FROM staging.orders WHERE carrier_ts < approved_ts",
        (
            _q(
                "orders", "x.order_id", "K1", RINGAN,
                f"{_ts('x.order_delivered_carrier_date')} < {_ts('x.order_approved_at')}",
            ),
        ),
    ),
    Rule(
        "K2", CONSISTENCY, BERAT, "tanggal tiba tidak lebih awal dari tanggal pesanan",
        "SELECT count(*) FROM raw.orders WHERE NULLIF(order_delivered_customer_date, '') IS NOT NULL "
        "AND NULLIF(order_purchase_timestamp, '') IS NOT NULL",
        "SELECT count(*) FROM raw.orders WHERE "
        f"{_ts('order_delivered_customer_date')} < {_ts('order_purchase_timestamp')}",
        "SELECT count(*) FROM staging.orders WHERE delivered_ts IS NOT NULL AND purchase_ts IS NOT NULL",
        "SELECT count(*) FROM staging.orders WHERE delivered_ts < purchase_ts",
        (
            _q(
                "orders", "x.order_id", "K2", BERAT,
                f"{_ts('x.order_delivered_customer_date')} < {_ts('x.order_purchase_timestamp')}",
            ),
        ),
    ),
    Rule(
        "K3", CONSISTENCY, BERAT, "seller_id dan product_id pada item ada di tabel induknya",
        _count("raw.order_items"),
        "SELECT count(*) FROM raw.order_items i WHERE "
        "NOT EXISTS (SELECT 1 FROM raw.sellers s WHERE s.seller_id = i.seller_id) "
        "OR NOT EXISTS (SELECT 1 FROM raw.products p WHERE p.product_id = i.product_id)",
        _count("staging.order_items"),
        "SELECT count(*) FROM staging.order_items i WHERE "
        "NOT EXISTS (SELECT 1 FROM staging.sellers s WHERE s.seller_id = i.seller_id) "
        "OR NOT EXISTS (SELECT 1 FROM staging.products p WHERE p.product_id = i.product_id)",
        (
            _q(
                "order_items", "x.order_id || '/' || x.order_item_id", "K3", BERAT,
                "NOT EXISTS (SELECT 1 FROM raw.sellers s WHERE s.seller_id = x.seller_id) "
                "OR NOT EXISTS (SELECT 1 FROM raw.products p WHERE p.product_id = x.product_id)",
            ),
        ),
    ),
    Rule(
        "K4", CONSISTENCY, RINGAN, "kode pos pelanggan dan penjual ada di tabel geolokasi",
        "SELECT (SELECT count(*) FROM raw.customers) + (SELECT count(*) FROM raw.sellers)",
        "SELECT (SELECT count(*) FROM raw.customers c WHERE NOT EXISTS (SELECT 1 FROM raw.geolocation g "
        "WHERE g.geolocation_zip_code_prefix = c.customer_zip_code_prefix)) "
        "+ (SELECT count(*) FROM raw.sellers s WHERE NOT EXISTS (SELECT 1 FROM raw.geolocation g "
        "WHERE g.geolocation_zip_code_prefix = s.seller_zip_code_prefix))",
        "SELECT (SELECT count(*) FROM staging.customers) + (SELECT count(*) FROM staging.sellers)",
        "SELECT (SELECT count(*) FROM staging.customers c WHERE NOT EXISTS (SELECT 1 FROM staging.geolocation g "
        "WHERE g.zip_prefix = c.zip_prefix)) "
        "+ (SELECT count(*) FROM staging.sellers s WHERE NOT EXISTS (SELECT 1 FROM staging.geolocation g "
        "WHERE g.zip_prefix = s.zip_prefix))",
        (
            _q(
                "customers", "x.customer_id", "K4", RINGAN,
                "NOT EXISTS (SELECT 1 FROM raw.geolocation g WHERE g.geolocation_zip_code_prefix = x.customer_zip_code_prefix)",
            ),
            _q(
                "sellers", "x.seller_id", "K4", RINGAN,
                "NOT EXISTS (SELECT 1 FROM raw.geolocation g WHERE g.geolocation_zip_code_prefix = x.seller_zip_code_prefix)",
            ),
        ),
    ),
    Rule(
        "V1", VALIDITY, BERAT, "review_score bernilai 1 sampai 5",
        _count("raw.order_reviews"),
        "SELECT count(*) FROM raw.order_reviews WHERE review_score IS NULL "
        "OR review_score NOT IN ('1', '2', '3', '4', '5')",
        _count("staging.reviews"),
        "SELECT count(*) FROM staging.reviews WHERE score IS NULL OR score NOT BETWEEN 1 AND 5",
        (
            _q(
                "order_reviews", "x.review_id || '/' || x.order_id", "V1", BERAT,
                "x.review_score IS NULL OR x.review_score NOT IN ('1', '2', '3', '4', '5')",
            ),
        ),
    ),
    Rule(
        "V2", VALIDITY, BERAT, "price dan freight_value tidak negatif",
        _count("raw.order_items"),
        "SELECT count(*) FROM raw.order_items WHERE NULLIF(price, '')::numeric < 0 "
        "OR NULLIF(freight_value, '')::numeric < 0",
        _count("staging.order_items"),
        "SELECT count(*) FROM staging.order_items WHERE price < 0 OR freight_value < 0",
        (
            _q(
                "order_items", "x.order_id || '/' || x.order_item_id", "V2", BERAT,
                "NULLIF(x.price, '')::numeric < 0 OR NULLIF(x.freight_value, '')::numeric < 0",
            ),
        ),
    ),
    Rule(
        "V3", VALIDITY, RINGAN, "payment_value lebih dari nol",
        _count("raw.order_payments"),
        "SELECT count(*) FROM raw.order_payments WHERE NULLIF(payment_value, '')::numeric <= 0",
        _count("staging.payments"),
        "SELECT count(*) FROM staging.payments WHERE value <= 0",
        (
            _q(
                "order_payments", "x.order_id || '/' || x.payment_sequential", "V3", RINGAN,
                "NULLIF(x.payment_value, '')::numeric <= 0",
            ),
        ),
    ),
    Rule(
        "V4", VALIDITY, RINGAN, "koordinat berada dalam kotak perkiraan wilayah Brasil",
        _count("raw.geolocation"),
        "SELECT count(*) FROM raw.geolocation WHERE NOT COALESCE("
        "NULLIF(geolocation_lat, '')::numeric BETWEEN -34 AND 6 "
        "AND NULLIF(geolocation_lng, '')::numeric BETWEEN -74 AND -34, false)",
        _count("staging.geolocation"),
        "SELECT count(*) FROM staging.geolocation WHERE NOT COALESCE("
        "lat BETWEEN -34 AND 6 AND lng BETWEEN -74 AND -34, false)",
        (
            _q(
                "geolocation", "x.geolocation_zip_code_prefix", "V4", RINGAN,
                "NOT COALESCE(NULLIF(x.geolocation_lat, '')::numeric BETWEEN -34 AND 6 "
                "AND NULLIF(x.geolocation_lng, '')::numeric BETWEEN -74 AND -34, false)",
            ),
        ),
    ),
    Rule(
        "V5", VALIDITY, BERAT, "kode negara bagian termasuk 27 kode resmi",
        "SELECT (SELECT count(*) FROM raw.customers) + (SELECT count(*) FROM raw.sellers)",
        "SELECT (SELECT count(*) FROM raw.customers WHERE customer_state NOT IN (SELECT uf FROM dq.ref_state) "
        "OR customer_state IS NULL) + (SELECT count(*) FROM raw.sellers "
        "WHERE seller_state NOT IN (SELECT uf FROM dq.ref_state) OR seller_state IS NULL)",
        "SELECT (SELECT count(*) FROM staging.customers) + (SELECT count(*) FROM staging.sellers)",
        "SELECT (SELECT count(*) FROM staging.customers WHERE state NOT IN (SELECT uf FROM dq.ref_state) "
        "OR state IS NULL) + (SELECT count(*) FROM staging.sellers "
        "WHERE state NOT IN (SELECT uf FROM dq.ref_state) OR state IS NULL)",
        (
            _q(
                "customers", "x.customer_id", "V5", BERAT,
                "x.customer_state IS NULL OR x.customer_state NOT IN (SELECT uf FROM dq.ref_state)",
            ),
            _q(
                "sellers", "x.seller_id", "V5", BERAT,
                "x.seller_state IS NULL OR x.seller_state NOT IN (SELECT uf FROM dq.ref_state)",
            ),
        ),
    ),
)

assert len(RULES) == 16 and len({r.id for r in RULES}) == 16
