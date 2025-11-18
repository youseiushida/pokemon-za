from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

DEFAULT_DB_PATH = os.environ.get(
    "ZA_DB",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "za.sqlite3"),
)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def detect_json1_enabled(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT json(?)", ("[]",)).fetchone()
        return True
    except Exception:
        pass
    try:
        rows = conn.execute("PRAGMA compile_options").fetchall()
        return any("JSON1" in (r[0] if isinstance(r, (list, tuple)) else str(r)) for r in rows)
    except Exception:
        return False


def get_table_columns(conn: sqlite3.Connection, table: str) -> Set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {str(row[1]) for row in cur.fetchall()}


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def build_like(term: Optional[str]) -> Optional[str]:
    if term is None:
        return None
    return f"%{term}%"


def execute_query(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] | None = None,
) -> List[Dict[str, Any]]:
    cur = conn.execute(sql, tuple(params or []))
    return rows_to_dicts(cur.fetchall())


def execute_one(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] | None = None,
) -> Optional[Dict[str, Any]]:
    cur = conn.execute(sql, tuple(params or []))
    row = cur.fetchone()
    return dict(row) if row else None


