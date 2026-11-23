"""Simulasi aliran data: memutar ulang pesanan historis ke dw.live_feed per batch.

Ini SIMULASI (replay data historis), bukan stream sungguhan.
Jalankan: python -m etl.replay [--reset] [--max-batches N]
"""
from __future__ import annotations

import argparse
import time

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.config import settings
from etl.db import get_engine


def next_batch(engine: Engine, batch_size: int) -> int:
    """Masukkan `batch_size` pesanan berikutnya (urut tanggal beli) yang belum diputar. Return jumlah baris."""
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO dw.live_feed (order_id, purchase_ts, delay_days, is_late)
            SELECT o.order_id, d.date::timestamp, o.delay_days, o.is_late
            FROM dw.v_order o
            JOIN dw.dim_date d ON d.date_key = o.purchase_date_key
            WHERE NOT EXISTS (SELECT 1 FROM dw.live_feed l WHERE l.order_id = o.order_id)
            ORDER BY d.date, o.order_id
            LIMIT :n"""), {"n": batch_size})
        return res.rowcount


def reset(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE dw.live_feed RESTART IDENTITY"))


def run(engine: Engine, batch_size: int, interval: float, max_batches: int | None = None) -> int:
    total, n = 0, 0
    while max_batches is None or n < max_batches:
        got = next_batch(engine, batch_size)
        if got == 0:
            break
        total += got
        n += 1
        print(f"[replay] batch {n}: +{got} pesanan (total {total})", flush=True)
        if max_batches is None or n < max_batches:
            time.sleep(interval)
    return total


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reset", action="store_true", help="kosongkan live_feed sebelum mulai")
    p.add_argument("--max-batches", type=int, default=None)
    a = p.parse_args()
    engine = get_engine()
    if a.reset:
        reset(engine)
    run(engine, settings.replay_batch_size, settings.replay_interval_seconds, a.max_batches)


if __name__ == "__main__":
    main()
