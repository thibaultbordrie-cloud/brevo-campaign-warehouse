"""Run every analysis query and gather the results in one text report."""
from __future__ import annotations

from pathlib import Path

import duckdb


def _title(sql: str) -> str:
    """First comment line of a query, used as its title."""
    for line in sql.splitlines():
        line = line.strip()
        if line.startswith("--"):
            return line.lstrip("-").strip()
    return ""


def build_report(con: duckdb.DuckDBPyConnection, sql_dir: Path) -> str:
    """Return one text block per .sql file (sorted by name). A failing query is reported, not fatal."""
    parts = []
    for path in sorted(Path(sql_dir).glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        parts.append(f"=== {path.name} ===\n{_title(sql)}\n")
        try:
            parts.append(str(con.sql(sql)))
        except duckdb.Error as exc:
            parts.append(f"[ERROR] {exc}\n")
        parts.append("\n")
    return "\n".join(parts)
