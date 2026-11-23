"""Mesin data quality: menjalankan aturan, mencatat hasil, dan mengisi karantina."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection

from .db import run_sql, scalar
from .rules import INFO, RULES

Stage = Literal["raw", "clean"]


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    dimension: str
    severity: str
    checked: int
    failed: int

    @property
    def score(self) -> float | None:
        return None if self.checked == 0 else round((self.checked - self.failed) * 100 / self.checked, 2)


def new_run_id(conn: Connection) -> int:
    return scalar(conn, "SELECT nextval('dq.run_seq')")


def quarantine_raw(conn: Connection, run_id: int) -> dict[str, int]:
    """Menyalin baris pelanggar ke quarantine.rejected_row; mengembalikan jumlah per aturan."""
    for rule in RULES:
        for statement in rule.quarantine:
            run_sql(conn, statement, {"run_id": run_id})
    rows = conn.exec_driver_sql(
        "SELECT rule_id, count(*) FROM quarantine.rejected_row WHERE run_id = %s GROUP BY rule_id",
        (run_id,),
    ).all()
    return {rule_id: n for rule_id, n in rows}


def run_rules(conn: Connection, run_id: int, stage: Stage) -> list[RuleResult]:
    results: list[RuleResult] = []
    for rule in RULES:
        checked_sql, failed_sql = (
            (rule.raw_checked, rule.raw_failed) if stage == "raw" else (rule.clean_checked, rule.clean_failed)
        )
        result = RuleResult(
            rule.id, rule.dimension, rule.severity, scalar(conn, checked_sql), scalar(conn, failed_sql)
        )
        conn.exec_driver_sql(
            "INSERT INTO dq.rule_result (run_id, stage, rule_id, dimension, severity, description, checked, failed) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (run_id, stage, rule.id, rule.dimension, rule.severity, rule.description,
             result.checked, result.failed),
        )
        results.append(result)
    return results


def dimension_scores(results: list[RuleResult]) -> dict[str, float | None]:
    """Skor per dimensi = (diperiksa - gagal) / diperiksa; aturan info tidak dihitung."""
    totals: dict[str, list[int]] = {}
    for r in results:
        if r.severity == INFO:
            continue
        t = totals.setdefault(r.dimension, [0, 0])
        t[0] += r.checked
        t[1] += r.failed
    return {d: (None if c == 0 else round((c - f) * 100 / c, 2)) for d, (c, f) in totals.items()}
