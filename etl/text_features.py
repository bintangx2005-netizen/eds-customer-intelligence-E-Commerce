"""Data tidak terstruktur: sentimen dan topik keluhan dari komentar ulasan (Bahasa Portugis).

Pendekatan berbasis leksikon (config/lexicon.toml) agar hasilnya dapat diaudit dan dijalankan
tanpa mengunduh model. Ketepatannya diuji terhadap review_score pada laporan akhir.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import Connection

from .config import ROOT

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib

NO_COMMENT = "tanpa_komentar"
TOPICS = ("pengiriman", "kualitas", "tidak_sesuai", "layanan", "kemasan")
_NEGATION = re.compile(r"(?<![a-z0-9])nao (?:[a-z0-9]+ )?$")


@dataclass(frozen=True)
class TextResult:
    sentiment: str  # positif | negatif | netral | tanpa_komentar
    topics: frozenset[str]


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _compile(term: str) -> re.Pattern[str]:
    prefix = term.endswith("*")
    body = re.escape(term.rstrip("*"))
    return re.compile(r"(?<![a-z0-9])" + body + ("" if prefix else r"(?![a-z0-9])"))


@lru_cache(maxsize=1)
def _lexicon() -> dict:
    with open(ROOT / "config" / "lexicon.toml", "rb") as fh:
        raw = tomllib.load(fh)
    return {
        "positive": [_compile(t) for t in raw["sentiment"]["positive"]],
        "negative": [_compile(t) for t in raw["sentiment"]["negative"]],
        "topics": {name: [_compile(t) for t in raw["topics"][name]] for name in TOPICS},
    }


def analyze(text: str | None) -> TextResult:
    if text is None or not text.strip():
        return TextResult(NO_COMMENT, frozenset())
    norm = normalize(text)
    if not norm:
        return TextResult(NO_COMMENT, frozenset())
    lex = _lexicon()
    negative = sum(len(p.findall(norm)) for p in lex["negative"])
    positive = 0
    for pattern in lex["positive"]:
        for m in pattern.finditer(norm):
            if _NEGATION.search(norm[max(0, m.start() - 12): m.start()]):
                negative += 1  # "nao recomendo", "nao gostei" membalik polaritas
            else:
                positive += 1
    sentiment = "negatif" if negative > positive else "positif" if positive > negative else "netral"
    topics = frozenset(name for name, pats in lex["topics"].items() if any(p.search(norm) for p in pats))
    return TextResult(sentiment, topics)


def build_review_features(conn: Connection) -> int:
    """Membuat staging.review_text_features dari staging.reviews; mengembalikan jumlah baris."""
    conn.exec_driver_sql("DROP TABLE IF EXISTS staging.review_text_features")
    conn.exec_driver_sql(
        "CREATE TABLE staging.review_text_features (review_id text PRIMARY KEY, sentiment text NOT NULL, "
        + ", ".join(f"topik_{t} boolean NOT NULL" for t in TOPICS) + ")"
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    for review_id, comment in conn.exec_driver_sql("SELECT review_id, comment FROM staging.reviews"):
        res = analyze(comment)
        writer.writerow([review_id, res.sentiment, *["t" if t in res.topics else "f" for t in TOPICS]])
    buf.seek(0)
    with conn.connection.cursor() as cur:
        cur.copy_expert("COPY staging.review_text_features FROM STDIN WITH (FORMAT csv)", buf)
    return conn.exec_driver_sql("SELECT count(*) FROM staging.review_text_features").scalar()
