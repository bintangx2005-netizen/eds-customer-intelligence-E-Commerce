"""Mengambil cuaca harian historis per negara bagian dari Open-Meteo (tanpa kunci API).

Hasilnya disimpan sebagai JSON di data/external/weather/<UF>.json dan di-commit, sehingga
pipeline tetap bisa dijalankan tanpa internet. Jalankan: python -m etl.fetch_weather [--force]
Sumber: https://open-meteo.com/en/docs/historical-weather-api (lisensi CC BY 4.0, non-komersial).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import settings

API = "https://archive-api.open-meteo.com/v1/archive"

# Titik koordinat ibu kota tiap negara bagian (mewakili seluruh negara bagian: pendekatan kasar).
CAPITALS: dict[str, tuple[float, float]] = {
    "AC": (-9.9747, -67.8100), "AL": (-9.6658, -35.7353), "AP": (0.0349, -51.0694),
    "AM": (-3.1190, -60.0217), "BA": (-12.9714, -38.5014), "CE": (-3.7319, -38.5267),
    "DF": (-15.7939, -47.8828), "ES": (-20.3155, -40.3128), "GO": (-16.6869, -49.2648),
    "MA": (-2.5307, -44.3068), "MT": (-15.6014, -56.0979), "MS": (-20.4697, -54.6201),
    "MG": (-19.9167, -43.9345), "PA": (-1.4558, -48.4902), "PB": (-7.1195, -34.8450),
    "PR": (-25.4284, -49.2733), "PE": (-8.0476, -34.8770), "PI": (-5.0892, -42.8019),
    "RJ": (-22.9068, -43.1729), "RN": (-5.7945, -35.2110), "RS": (-30.0346, -51.2177),
    "RO": (-8.7612, -63.9039), "RR": (2.8235, -60.6758), "SC": (-27.5954, -48.5480),
    "SP": (-23.5505, -46.6333), "SE": (-10.9472, -37.0731), "TO": (-10.1689, -48.3317),
}


def _request_json(url: str, attempts: int = 5) -> dict:
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < attempts:  # batas kuota: tunggu lalu coba lagi
                time.sleep(60)
                continue
            raise
        except urllib.error.URLError:
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)
    raise RuntimeError("tidak terjangkau")  # pragma: no cover


def fetch_state(uf: str) -> dict:
    lat, lng = CAPITALS[uf]
    query = urllib.parse.urlencode({
        "latitude": lat, "longitude": lng,
        "start_date": settings.weather_start, "end_date": settings.weather_end,
        "daily": "precipitation_sum,temperature_2m_max", "timezone": settings.weather_timezone,
    })
    data = _request_json(f"{API}?{query}")
    daily = data.get("daily") or {}
    if not daily.get("time") or "precipitation_sum" not in daily:
        raise RuntimeError(f"Respons Open-Meteo untuk {uf} tidak berisi data harian: {str(data)[:200]}")
    return data


def ensure(weather_dir: Path, force: bool = False, pause: float = 1.0) -> list[str]:
    """Mengunduh JSON yang belum ada (atau semuanya bila force); mengembalikan daftar UF yang diunduh."""
    weather_dir.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    for uf in CAPITALS:
        target = weather_dir / f"{uf}.json"
        if target.exists() and not force:
            continue
        target.write_text(json.dumps(fetch_state(uf), separators=(",", ":")), encoding="utf-8")
        fetched.append(uf)
        time.sleep(pause)
    return fetched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="unduh ulang semua negara bagian")
    args = parser.parse_args()
    done = ensure(settings.weather_dir, force=args.force)
    print(f"Diunduh: {', '.join(done) if done else 'tidak ada (semua sudah ada)'}")


if __name__ == "__main__":
    main()
