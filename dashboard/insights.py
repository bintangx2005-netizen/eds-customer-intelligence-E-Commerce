"""Business insight dan rekomendasi yang dihitung dari data (bukan teks tetap).

Kalimat bersifat asosiasi dari data observasional, bukan bukti sebab-akibat.
"""
from __future__ import annotations

import pandas as pd


def _ok(df: pd.DataFrame | None) -> bool:
    return df is not None and len(df) > 0


def build(kpi: pd.Series, rating_delay: pd.DataFrame, late_state: pd.DataFrame, topics: pd.DataFrame,
          bad_review: pd.DataFrame, concentration: pd.DataFrame, rain: pd.DataFrame) -> list[dict]:
    out: list[dict] = []

    if _ok(rating_delay) and len(rating_delay) >= 2:
        best, worst = rating_delay.iloc[0], rating_delay.iloc[-1]
        gap = float(best.rata_rating) - float(worst.rata_rating)
        out.append({
            "judul": "Keterlambatan berkaitan dengan rating rendah",
            "insight": (f"Pesanan kelompok '{worst.kelompok[3:]}' rata-rata berating {worst.rata_rating}, "
                        f"sedangkan '{best.kelompok[3:]}' berating {best.rata_rating} (selisih {gap:.2f} bintang)."),
            "rekomendasi": "Jadikan ketepatan pengiriman indikator utama layanan dan pantau mingguan; "
                           "beri peringatan dini pada pesanan yang diperkirakan melewati estimasi.",
        })

    if _ok(bad_review) and len(bad_review) == 2:
        d = bad_review.set_index("kelompok")["pct_ulasan_buruk"]
        late, ontime = float(d["Terlambat"]), float(d["Tepat waktu"])
        ratio = late / ontime if ontime else float("nan")
        out.append({
            "judul": "Pesanan terlambat lebih sering mendapat ulasan 1-2 bintang",
            "insight": (f"{late}% pesanan terlambat berulasan buruk (1-2 bintang) dibanding {ontime}% pada "
                        f"pesanan tepat waktu" + (f", sekitar {ratio:.1f} kali lebih sering." if ratio == ratio else ".")),
            "rekomendasi": "Hubungi pembeli proaktif saat pesanan akan terlambat (informasi status, "
                           "kompensasi kecil) untuk menekan ulasan buruk.",
        })

    if _ok(late_state) and _ok(kpi.to_frame()):
        nat = float(kpi.pct_terlambat)
        worst = late_state[late_state.pesanan >= 200].head(3)
        if len(worst):
            names = ", ".join(f"{r.uf} ({r.pct_terlambat}%)" for r in worst.itertuples())
            out.append({
                "judul": "Keterlambatan terkonsentrasi di wilayah tertentu",
                "insight": f"Rata-rata nasional {nat}% terlambat; tertinggi: {names}.",
                "rekomendasi": "Prioritaskan perbaikan logistik (gudang/mitra kurir, estimasi lebih realistis) "
                               "di wilayah tersebut sebelum wilayah lain.",
            })

    if _ok(concentration) and concentration.iloc[0].pct_terlambat_dari_top5 == concentration.iloc[0].pct_terlambat_dari_top5:
        c = concentration.iloc[0]
        out.append({
            "judul": "Sebagian kecil penjual menyumbang banyak keterlambatan",
            "insight": f"5% penjual teratas (dari {int(c.penjual)} penjual dengan >=10 pesanan terkirim) "
                       f"menyumbang {c.pct_terlambat_dari_top5}% pesanan terlambat.",
            "rekomendasi": "Fokuskan pembinaan atau peringatan pada penjual dengan keterlambatan terbanyak, "
                           "bukan pada seluruh penjual (lihat halaman Penjual).",
        })

    if _ok(topics):
        t = topics.iloc[0]
        share = float(t.ulasan) * 100 / float(topics.ulasan.sum())
        out.append({
            "judul": "Keluhan utama pada ulasan 1-2 bintang",
            "insight": f"Topik terbanyak: '{t.topic}' ({int(t.ulasan):,} ulasan, {share:.0f}% dari semua topik "
                       "keluhan). Satu ulasan bisa memuat lebih dari satu topik; hasil dari leksikon sederhana.",
            "rekomendasi": "Prioritaskan perbaikan pada topik keluhan terbesar, lalu validasi dengan "
                           "pembacaan sampel ulasan sebelum mengambil keputusan.",
        })

    if _ok(rain) and not (len(rain) == 1 and rain.iloc[0].kondisi == "Tidak ada data cuaca"):
        r = rain[rain.kondisi != "Tidak ada data cuaca"].set_index("kondisi")["pct_terlambat"]
        heavy = [k for k in r.index if k.startswith("Hujan lebat")]
        dry = [k for k in r.index if k.startswith("Kering")]
        if heavy and dry:
            out.append({
                "judul": "Hujan lebat selama pengiriman",
                "insight": f"Pesanan yang melewati hujan lebat terlambat {r[heavy[0]]}% vs {r[dry[0]]}% "
                           "pada kondisi kering/ringan (asosiasi, belum tentu sebab).",
                "rekomendasi": "Tambahkan margin estimasi pada pengiriman ke wilayah yang sedang hujan lebat.",
            })
    return out
