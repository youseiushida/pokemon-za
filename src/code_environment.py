# src/code_environment.py
from __future__ import annotations

import io
import json
import math
import re
import sqlite3
import statistics
import multiprocessing
from multiprocessing import Process, Queue
from contextlib import redirect_stdout
from typing import Any, Dict, Optional

from src.db import DEFAULT_DB_PATH


def _open_ro_conn(db_path: Optional[str]) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    # Read-only URI で開く
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # 書き込み不可にする（更に保険）
    try:
        conn.execute("PRAGMA query_only = ON")
    except Exception:
        pass
    return conn


def _safe_builtins() -> Dict[str, Any]:
    # 必要最低限の安全な builtin のみ許可（ファイルIO/exec/eval/__import__ は除外）
    return {
        "print": print,
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "len": len,
        "range": range,
        "enumerate": enumerate,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "sorted": sorted,
        "any": any,
        "all": all,
        "zip": zip,
        "map": map,
        "filter": filter,
        "round": round,
    }


def run_user_code(code: str, db_path: Optional[str] = None, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    ユーザーコードを安全サンドボックスで実行し、結果と標準出力を返す。
    - conn は読み取り専用
    - sql(query, params=()) で list[dict] 取得
    - scalar(query, params=()) で単一値取得
    - ユーザーは変数 result に最終結果を代入する（JSON シリアライズ可能な値）
    """
    args = args or {}
    conn = _open_ro_conn(db_path)

    def sql(query: str, params: Any = ()):
        cur = conn.execute(query, params if isinstance(params, (list, tuple)) else (params,))
        return [dict(r) for r in cur.fetchall()]

    def scalar(query: str, params: Any = ()):
        cur = conn.execute(query, params if isinstance(params, (list, tuple)) else (params,))
        row = cur.fetchone()
        return None if row is None else (row[0] if len(row.keys()) == 1 else dict(row))

    # 実行環境（globals/locals を同一 dict にすることで関数内からも参照可能にする）
    env: Dict[str, Any] = {
        "__builtins__": _safe_builtins(),
        # よく使う標準ライブラリを前置提供（import を禁止しているため）
        "math": math,
        "statistics": statistics,
        "json": json,
        "re": re,
        # 実行ヘルパ
        "conn": conn,     # 読み取り専用
        "sql": sql,       # SELECT ヘルパ
        "scalar": scalar, # 単一値ヘルパ
        "args": args,     # ユーザー指定の任意パラメータ
        "result": None,   # 結果の受け渡し用
    }

    stdout_io = io.StringIO()
    try:
        with redirect_stdout(stdout_io):
            exec(code, env, env)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    out = {
        "stdout": stdout_io.getvalue(),
        "result": env.get("result", None),
    }
    return out


def _worker_run_code(code: str, db_path: Optional[str], args: Optional[Dict[str, Any]], q: Queue) -> None:
    """Child process worker to safely execute user code and return results via a Queue."""
    try:
        out = run_user_code(code=code, db_path=db_path, args=args or {})
        # Cap stdout length to avoid excessive payloads
        if isinstance(out, dict) and "stdout" in out and isinstance(out["stdout"], str):
            out["stdout"] = out["stdout"][:10000]
        q.put({"ok": True, "data": out})
    except Exception as e:
        q.put({"ok": False, "error": str(e)})


def run_user_code_with_timeout(
    code: str,
    db_path: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
    timeout_sec: float = 8.0,
) -> Dict[str, Any]:
    """
    Execute user code in a separate process with a timeout (Windows-safe).
    Returns {result, stdout} or {error}.
    """
    q: Queue = multiprocessing.Queue()
    p: Process = multiprocessing.Process(target=_worker_run_code, args=(code, db_path, args, q))
    p.start()
    p.join(timeout_sec)
    if p.is_alive():
        p.terminate()
        p.join(1)
        return {"result": None, "stdout": "", "error": f"timeout after {timeout_sec}s"}
    if q.empty():
        return {"result": None, "stdout": "", "error": "no result (crash or empty output)"}
    msg = q.get()
    if not isinstance(msg, dict) or not msg.get("ok"):
        return {"result": None, "stdout": "", "error": str(msg.get("error", "unknown error"))}
    return msg["data"]


if __name__ == "__main__":
    # デモ: 「ソーラービーム」を覚える くさ タイプ かつ とくこう >= 100 のポケモンを検索
    demo_code = r'''
# 列名の差異（sp_attack/sp_atk/spa）に対応
cols = [r["name"] for r in sql("PRAGMA table_info(pokemons)")]
def pick(*cands):
    for c in cands:
        if c in cols:
            return c
    return None

spa_col = pick("sp_attack", "sp_atk", "spa")
if spa_col is None:
    raise ValueError("とくこう列が見つかりません（sp_attack/sp_atk/spa のいずれかが必要）")

query = f"""
SELECT p.*
FROM pokemons p
JOIN pokemon_moves pm ON pm.pokemon_id = p.id
JOIN moves m ON m.id = pm.move_id
WHERE m.name = ?
  AND p.types_json LIKE ?
  AND p.{spa_col} >= ?
GROUP BY p.id
ORDER BY p.{spa_col} DESC, p.name ASC
"""

rows = sql(query, ["ソーラービーム", '%"くさ"%', 100])
result = [r["name"] for r in rows]
print(f"hit={len(rows)}")
'''
    out = run_user_code(demo_code)
    print(json.dumps(out, ensure_ascii=False, indent=2))