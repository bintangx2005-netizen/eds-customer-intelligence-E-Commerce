# Customer Intelligence E-Commerce (Olist) — Prototipe EDS

Prototipe sistem data perusahaan untuk proyek akhir Enterprise Data System. Menggabungkan tiga sumber
(Olist e-commerce, Olist Marketing Funnel, cuaca Open-Meteo), mengukur kualitas data sebelum/sesudah
pembersihan, membangun data warehouse bintang di PostgreSQL, dan menampilkannya di dashboard Streamlit.

## Arsitektur singkat

`data/raw/*.csv` + cuaca JSON → schema `raw` (teks) → `staging` (bertipe, baris bermasalah dikarantina)
→ `dw` (skema bintang) → dashboard. Hasil aturan kualitas ada di schema `dq`, baris bermasalah di `quarantine`.
Pipeline idempotent: dijalankan berulang menghasilkan `dw` yang sama; riwayat `dq` dan karantina tetap tersimpan per `run_id`.

## Langkah replikasi (Docker)

1. Pasang Docker Desktop.
2. Unduh dataset dari Kaggle (perlu akun gratis) dan taruh **11 file CSV** di `data/raw/`:
   - https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce (9 file)
   - https://www.kaggle.com/datasets/olistbr/marketing-funnel-olist (2 file: `olist_closed_deals_dataset.csv`, `olist_marketing_qualified_leads_dataset.csv`)
3. Jalankan: `docker compose up --build`
4. Buka http://localhost:8501 setelah layanan `etl` selesai.

Data cuaca (27 file `data/external/weather/<UF>.json`) diunduh otomatis dari Open-Meteo saat ETL bila belum ada
dan butuh internet. Bila sudah ada di repo, tidak diunduh ulang. Manual: `python -m etl.fetch_weather`.

Simulasi aliran data (replay data historis, bukan stream sungguhan): `docker compose --profile sim up replay`.

### Jumlah baris kontrol (raw)

customers 99.441 · geolocation 1.000.163 · order_items 112.650 · payments 103.886 · reviews 99.224 ·
orders 99.441 · products 32.951 · sellers 3.095 · category_translation 71 · closed_deals 842 · mql 8.000

Ringkasan ini dicetak juga di akhir log ETL; bila angkanya berbeda, berkas CSV Anda tidak sama dengan yang kami pakai.

## Tanpa Docker

```
python -m venv venv && venv\Scripts\activate      # Windows (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
# siapkan PostgreSQL 16 dengan user/db/password eds, lalu:
set EDS_DATABASE_URL=postgresql+psycopg2://eds:eds@localhost:5432/eds
python -m etl.run
set DASHBOARD_DATABASE_URL=postgresql+psycopg2://analyst:analyst@localhost:5432/eds
streamlit run dashboard/app.py
```

## Tata kelola akses (peran database)

| Peran | Akses | Kata sandi bawaan |
|---|---|---|
| `analyst` | baca `dw` dan tampilan `dq` saja (dipakai dashboard) | `analyst` |
| `steward` | baca `raw`, `quarantine`, `dq`; ubah status karantina | `steward` |
| `engineer` | semua | `engineer` |

Ganti lewat env `EDS_ANALYST_PASSWORD`, `EDS_STEWARD_PASSWORD`, `EDS_ENGINEER_PASSWORD`. Kata sandi bawaan hanya untuk demo lokal.

## Menjalankan pengujian

```
pip install -r requirements-dev.txt
python -m pytest -q
```

## Catatan jujur tentang keterbatasan

- Analisis teks memakai leksikon bahasa Portugis, bukan model ML; akurasinya terbatas dan divalidasi terhadap rating bintang di laporan akhir.
- Skor U3 dan V4 dihitung per baris pada `raw` tetapi per kode pos pada tahap bersih, jadi perbandingan sebelum/sesudah keduanya tidak setara langsung.
- Pengukuran "sesudah" dilakukan pada tabel `staging` yang menjadi sumber `dw`.
- "Aliran data" di dashboard adalah replay simulasi.
- Pengujian otomatis memakai PostgreSQL lokal dan fixture kecil; konfigurasi Docker belum diuji di lingkungan pengembangan kami selain lewat panduan ini.
- Data Olist berlisensi CC BY-NC-SA 4.0; Open-Meteo gratis untuk non-komersial.
