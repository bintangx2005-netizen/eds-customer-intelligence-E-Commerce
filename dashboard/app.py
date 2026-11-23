"""Dashboard Customer Intelligence Olist (Streamlit). Jalankan: streamlit run dashboard/app.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # agar `dashboard` bisa diimpor

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import queries as q  # noqa: E402

st.set_page_config(page_title="Customer Intelligence Olist", layout="wide")


@st.cache_resource
def engine():
    return q.get_engine()


@st.cache_data(ttl=300, show_spinner=False)
def cached(fn_name: str, **kw):
    return getattr(q, fn_name)(engine(), **kw)


def page_kpi() -> None:
    st.header("Ringkasan KPI")
    k = cached("kpi").iloc[0]
    c = st.columns(4)
    c[0].metric("Pesanan", f"{int(k.pesanan):,}")
    c[1].metric("Terlambat", f"{k.pct_terlambat}%")
    c[2].metric("Rata-rata rating", f"{k.rata_rating}")
    c[3].metric("Nilai barang (BRL)", f"{int(k.nilai_barang):,}")

    st.subheader("Simulasi aliran data (replay data historis, bukan stream sungguhan)")
    st.caption("Pesanan diputar ulang ke tabel dw.live_feed oleh `python -m etl.replay`. "
               "Panel di bawah menyegarkan diri tiap 5 detik.")

    @st.fragment(run_every=5)
    def live() -> None:
        s = q.live_feed_summary(engine()).iloc[0]
        a, b, t = st.columns(3)
        a.metric("Pesanan diterima (simulasi)", f"{int(s.diterima):,}")
        b.metric("% terlambat (simulasi)", f"{s.pct_terlambat}%")
        t.metric("Pembaruan terakhir", str(s.terakhir)[:19] if s.terakhir is not None else "-")
        if int(s.diterima) == 0:
            st.info("Belum ada data simulasi. Jalankan: docker compose --profile sim up replay")
        else:
            st.dataframe(q.live_feed_recent(engine()), use_container_width=True, hide_index=True)

    live()


def page_delay() -> None:
    st.header("Keterlambatan pengiriman")
    d = cached("rating_by_delay")
    st.plotly_chart(px.bar(d, x="kelompok", y="rata_rating", text="rata_rating",
                           hover_data=["pesanan"], title="Rata-rata rating menurut ketepatan kirim"),
                    use_container_width=True)
    s = cached("late_by_state")
    st.plotly_chart(px.bar(s, x="uf", y="pct_terlambat", color="region", hover_data=["pesanan"],
                           title="% terlambat per negara bagian pembeli"), use_container_width=True)
    r = cached("rain_effect")
    st.plotly_chart(px.bar(r, x="kondisi", y="pct_terlambat", hover_data=["pesanan"],
                           title="% terlambat menurut hujan terberat selama pengiriman"),
                    use_container_width=True)
    if (r["kondisi"] == "Tidak ada data cuaca").any() and len(r) == 1:
        st.warning("Data cuaca belum dimuat. Jalankan `python -m etl.fetch_weather` lalu ulangi ETL.")


def page_sellers() -> None:
    st.header("Penjual")
    min_orders = st.slider("Minimal pesanan terkirim", 10, 200, 30)
    st.dataframe(cached("seller_ranking", min_orders=min_orders), use_container_width=True, hide_index=True)
    st.subheader("Penjual via funnel pemasaran vs non-funnel")
    st.dataframe(cached("funnel_comparison"), use_container_width=True, hide_index=True)
    st.caption("Ulasan melekat pada pesanan; pesanan multi-penjual berbagi skor yang sama.")


def page_topics() -> None:
    st.header("Topik ulasan (leksikon Portugis, bukan model ML)")
    t = cached("topics_negative")
    st.plotly_chart(px.bar(t, x="topic", y="ulasan", title="Topik pada ulasan rating 1-2"),
                    use_container_width=True)
    sv = cached("sentiment_vs_score")
    st.subheader("Validasi: sentimen leksikon vs rating bintang")
    st.dataframe(sv, use_container_width=True, hide_index=True)
    st.caption("Akurasi leksikon terbatas; rating bintang dipakai sebagai pembanding kasar.")


def page_dq() -> None:
    st.header("Kualitas data")
    d = cached("dq_dimension")
    st.plotly_chart(px.bar(d, x="dimension", y="score", color="stage", barmode="group",
                           range_y=[0, 100], title="Skor kualitas per dimensi: raw vs setelah pembersihan"),
                    use_container_width=True)
    st.caption("Catatan: aturan U3 dan V4 dihitung per baris pada raw tetapi per kode pos pada tahap "
               "bersih, sehingga perbandingan sebelum/sesudah keduanya tidak setara langsung. "
               "Dimensi 'info' (C4) tidak masuk skor.")
    st.subheader("Hasil per aturan")
    st.dataframe(cached("dq_rules"), use_container_width=True, hide_index=True)
    st.subheader("Antrean karantina")
    st.dataframe(cached("quarantine_summary"), use_container_width=True, hide_index=True)


PAGES = {"Ringkasan KPI": page_kpi, "Keterlambatan": page_delay, "Penjual": page_sellers,
         "Topik ulasan": page_topics, "Kualitas data": page_dq}

choice = st.sidebar.radio("Halaman", list(PAGES))
st.sidebar.caption("Terhubung sebagai peran `analyst` (hanya-baca).")
try:
    PAGES[choice]()
except Exception as e:  # tampilkan pesan jelas jika DB belum siap
    st.error(f"Gagal membaca database: {e}")
    st.info("Pastikan ETL sudah selesai (`docker compose up`) dan DASHBOARD_DATABASE_URL benar.")
