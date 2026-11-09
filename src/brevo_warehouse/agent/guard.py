"""Guard rails: the agent can only READ the warehouse, a little at a time.

Three locks, each enough on its own:
1. the connection is opened read-only, with file and network access switched off;
2. the SQL text must be a single SELECT (or WITH ... SELECT), without dangerous words;
3. results are capped (MAX_ROWS) and every query is stopped after TIMEOUT_S seconds.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

import duckdb

MAX_ROWS = 200
TIMEOUT_S = 15

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|attach|detach|copy|export|import"
    r"|install|load|pragma|set|reset|call|checkpoint|vacuum|grant|revoke|use)\b"
    r"|\b(read_csv\w*|read_parquet|read_json\w*|read_text|read_blob|parquet_scan|glob|sniff_csv"
    r"|getenv|duckdb_secrets|duckdb_settings)\s*\(",
    re.IGNORECASE,
)


class GuardError(ValueError):
    """The SQL was refused before reaching the database."""


def _strip(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql.strip().rstrip(";").strip()


def _outside_quotes(sql: str) -> str:
    """The SQL with every quoted string emptied, so words inside strings are not checked."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_sql(sql: str) -> str:
    """Return the cleaned SQL, or raise GuardError explaining the refusal."""
    clean = _strip(sql)
    if not clean:
        raise GuardError("requête vide")
    bare = _outside_quotes(clean)
    if ";" in bare:
        raise GuardError("une seule requête à la fois")
    if not re.match(r"(?is)^\s*(select|with)\b", bare):
        raise GuardError("seules les requêtes SELECT sont autorisées")
    found = FORBIDDEN.search(bare)
    if found:
        raise GuardError(f"mot interdit : {found.group(0).strip('( ')}")
    return clean


def connect_read_only(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True, config={"enable_external_access": False})


def run_query(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[list[str], list[tuple]]:
    """Run a checked query with a row cap and a timeout. Returns (columns, rows)."""
    clean = check_sql(sql)
    timer = threading.Timer(TIMEOUT_S, con.interrupt)
    timer.start()
    try:
        cur = con.execute(f"SELECT * FROM ({clean}) AS agent_query LIMIT {MAX_ROWS}")
        columns = [d[0] for d in cur.description]
        return columns, cur.fetchall()
    finally:
        timer.cancel()
