from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple
import os

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from src.db import (
    DEFAULT_DB_PATH,
    build_like,
    detect_json1_enabled,
    execute_one,
    execute_query,
    get_connection,
    get_table_columns,
)


# -----------------------------
# Pydantic models (inputs/outputs with docs)
# -----------------------------
class SearchPokemonsInput(BaseModel):
    name_like: Optional[str] = Field(None, description="ポケモン名の部分一致（%...%）")
    types: Optional[List[str]] = Field(None, description="タイプで絞り込み。例: ['くさ','フェアリー']")
    type_mode: Literal["any", "all"] = Field("any", description="'any'=いずれか一致 / 'all'=全て一致")
    dex_no_min: Optional[int] = Field(None, description="図鑑番号の下限")
    dex_no_max: Optional[int] = Field(None, description="図鑑番号の上限")
    hp_min: Optional[int] = Field(None, description="HPの下限")
    hp_max: Optional[int] = Field(None, description="HPの上限")
    attack_min: Optional[int] = Field(None, description="こうげき(attack/atk)の下限")
    attack_max: Optional[int] = Field(None, description="こうげき(attack/atk)の上限")
    defense_min: Optional[int] = Field(None, description="ぼうぎょ(defense/def)の下限")
    defense_max: Optional[int] = Field(None, description="ぼうぎょ(defense/def)の上限")
    sp_attack_min: Optional[int] = Field(None, description="とくこう(sp_attack/sp_atk/spa)の下限")
    sp_attack_max: Optional[int] = Field(None, description="とくこう(sp_attack/sp_atk/spa)の上限")
    sp_defense_min: Optional[int] = Field(None, description="とくぼう(sp_defense/sp_def/spd)の下限")
    sp_defense_max: Optional[int] = Field(None, description="とくぼう(sp_defense/sp_def/spd)の上限")
    speed_min: Optional[int] = Field(None, description="すばやさ(speed/spe)の下限")
    speed_max: Optional[int] = Field(None, description="すばやさ(speed/spe)の上限")
    bst_min: Optional[int] = Field(None, description="種族値合計(bst/total/sum)の下限")
    bst_max: Optional[int] = Field(None, description="種族値合計(bst/total/sum)の上限")
    obtain_method_like: Optional[str] = Field(None, description="入手方法の部分一致（%...%）")
    sort: Optional[List[str]] = Field(None, description='並び順。例: ["-bst","speed"]（先頭の-で降順）')
    limit: int = Field(10, description="取得件数（デフォルト10）")
    offset: int = Field(0, description="スキップ件数")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name_like": "フシ",
                    "types": ["くさ", "フェアリー"],
                    "type_mode": "any",
                    "bst_min": 400,
                    "sort": ["-bst", "speed"],
                    "limit": 10,
                    "offset": 0,
                }
            ]
        }
    }


class SearchMovesInput(BaseModel):
    name_like: Optional[str] = Field(None, description="技名の部分一致（%...%）")
    type: Optional[List[str]] = Field(None, description="タイプで絞り込み。例: ['かくとう']")
    category: Optional[List[str]] = Field(None, description="分類。例: ['物理','特殊','変化']")
    power_min: Optional[int] = Field(None, description="威力の下限")
    power_max: Optional[int] = Field(None, description="威力の上限")
    activation_time_min: Optional[float] = Field(None, description="発動時間の下限[s]")
    activation_time_max: Optional[float] = Field(None, description="発動時間の上限[s]")
    startup_time_min: Optional[float] = Field(None, description="発生までの下限[s]")
    startup_time_max: Optional[float] = Field(None, description="発生までの上限[s]")
    startup_time_q_min: Optional[float] = Field(None, description="発生まで(せんせいのツメ) の下限[s]")
    startup_time_q_max: Optional[float] = Field(None, description="発生まで(せんせいのツメ) の上限[s]")
    recovery_time_min: Optional[float] = Field(None, description="硬直時間の下限[s]")
    recovery_time_max: Optional[float] = Field(None, description="硬直時間の上限[s]")
    total_time_min: Optional[float] = Field(None, description="全体時間の下限[s]")
    total_time_max: Optional[float] = Field(None, description="全体時間の上限[s]")
    dps_min: Optional[float] = Field(None, description="DPS の下限")
    dps_max: Optional[float] = Field(None, description="DPS の上限")
    direct_attack: Optional[Literal["接触", "×"]] = Field(None, description="直接攻撃フラグ。'接触' or '×'")
    finger_wag: Optional[Literal["出る", "出ない"]] = Field(None, description="ゆびをふる。'出る' or '出ない'")
    protect: Optional[Literal["－", "通常"]] = Field(None, description="まもる。'－' or '通常'")
    substitute: Optional[Literal["－", "通常"]] = Field(None, description="みがわり。'－' or '通常'")
    range_like: Optional[str] = Field(None, description="範囲の部分一致（%...%）")
    sort: Optional[List[str]] = Field(None, description='並び順。例: ["-dps","total_time"]')
    limit: int = Field(10, description="取得件数（デフォルト10）")
    offset: int = Field(0, description="スキップ件数")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name_like": "パンチ",
                    "type": ["かくとう"],
                    "category": ["物理"],
                    "direct_attack": "接触",
                    "finger_wag": "出る",
                    "protect": "通常",
                    "substitute": "－",
                    "dps_min": 5.0,
                    "sort": ["-dps", "total_time"],
                    "limit": 10,
                }
            ]
        }
    }


class SearchPokemonsOutput(BaseModel):
    items: List[Dict[str, Any]] = Field(..., description="ポケモン行のリスト（DB列をすべて含む）")
    limit: int = Field(..., description="返却件数")
    offset: int = Field(..., description="スキップ件数")


class SearchMovesOutput(BaseModel):
    items: List[Dict[str, Any]] = Field(..., description="技行のリスト（DB列をすべて含む）")
    limit: int = Field(..., description="返却件数")
    offset: int = Field(..., description="スキップ件数")


class PokemonMoveItem(BaseModel):
    learn_method: Optional[str] = Field(None, description="覚え方（基本/レベル/技マシン）")
    level: Optional[int] = Field(None, description="レベル（覚えられない場合は -1）")
    tm_no: Optional[int] = Field(None, description="技マシン番号（覚えられない場合は -1）")
    move: Dict[str, Any] = Field(..., description="技の詳細（DB列）")


class PokemonDetailOutput(BaseModel):
    pokemon: Dict[str, Any] = Field(..., description="ポケモン詳細（DB列）")
    moves: List[PokemonMoveItem] = Field(..., description="覚える技リスト（覚え方付き）")


class MovePokemonItem(BaseModel):
    learn_method: Optional[str] = Field(None, description="覚え方（基本/レベル/技マシン）")
    level: Optional[int] = Field(None, description="レベル（覚えられない場合は -1）")
    tm_no: Optional[int] = Field(None, description="技マシン番号（覚えられない場合は -1）")
    pokemon: Dict[str, Any] = Field(..., description="ポケモン詳細（DB列）")


class MoveDetailOutput(BaseModel):
    move: Dict[str, Any] = Field(..., description="技詳細（DB列）")
    pokemons: List[MovePokemonItem] = Field(..., description="この技を覚えるポケモン（覚え方付き）")


class RunCodeInput(BaseModel):
    code: str = Field(..., description="実行する Python コード（result に結果を代入）")
    db_path: Optional[str] = Field(None, description="SQLite のパス（未指定時は既定の za.sqlite3）")
    args: Optional[Dict[str, Any]] = Field(None, description="ユーザー任意の引数(dict)")


class RunCodeOutput(BaseModel):
    result: Any = Field(None, description="ユーザーコード内で代入された result の値")
    stdout: str = Field("", description="print 出力")


class GetPokemonDetailInput(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None


class GetMoveDetailInput(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None


# -----------------------------
# Helpers
# -----------------------------
def _parse_sort(sort_list: Optional[List[str]], allowed: List[str]) -> str:
    if not sort_list:
        return ""
    order_clauses: List[str] = []
    allowed_set = set(allowed)
    for raw in sort_list:
        direction = "ASC"
        key = raw
        if raw.startswith("-"):
            direction = "DESC"
            key = raw[1:]
        if key not in allowed_set:
            raise ValueError(f"Unsupported sort field: {key}")
        order_clauses.append(f"{key} {direction}")
    return (" ORDER BY " + ", ".join(order_clauses)) if order_clauses else ""


def _select_existing_columns(table_cols: List[str], existing: List[str]) -> List[str]:
    existing_set = set(existing)
    return [c for c in table_cols if c in existing_set]


# -----------------------------
# search_pokemons
# -----------------------------
def search_pokemons_handler(payload: SearchPokemonsInput) -> Dict[str, Any]:
    conn = get_connection()
    try:
        json1 = detect_json1_enabled(conn)
        pcols = list(get_table_columns(conn, "pokemons"))
    finally:
        pass

    # Select all columns to keep compatibility with varying schemas
    select_cols_sql = "*"

    def _resolve(col_candidates: List[str]) -> Optional[str]:
        for c in col_candidates:
            if c in pcols:
                return c
        return None

    where: List[str] = []
    params: List[Any] = []

    if payload.name_like:
        where.append("name LIKE ?")
        params.append(build_like(payload.name_like))
    if payload.obtain_method_like:
        where.append("obtain_method LIKE ?")
        params.append(build_like(payload.obtain_method_like))

    # Numeric ranges
    ranged_specs: List[Tuple[List[str], Optional[int], Optional[int]]] = [
        (["dex_no"], payload.dex_no_min, payload.dex_no_max),
        (["hp"], payload.hp_min, payload.hp_max),
        (["attack", "atk"], payload.attack_min, payload.attack_max),
        (["defense", "def"], payload.defense_min, payload.defense_max),
        (["sp_attack", "sp_atk", "spa"], payload.sp_attack_min, payload.sp_attack_max),
        (["sp_defense", "sp_def", "spd"], payload.sp_defense_min, payload.sp_defense_max),
        (["speed", "spe"], payload.speed_min, payload.speed_max),
        (["bst", "total", "sum"], payload.bst_min, payload.bst_max),
    ]
    for candidates, mn, mx in ranged_specs:
        col = _resolve(candidates)
        if not col:
            continue
        if mn is not None:
            where.append(f"{col} >= ?")
            params.append(mn)
        if mx is not None:
            where.append(f"{col} <= ?")
            params.append(mx)

    # Type filters
    if payload.types:
        types = [t for t in payload.types if t]
        if types:
            if json1:
                if payload.type_mode == "any":
                    placeholders = ",".join(["?"] * len(types))
                    where.append(
                        f"EXISTS (SELECT 1 FROM json_each(pokemons.types_json) je WHERE je.value IN ({placeholders}))"
                    )
                    params.extend(types)
                else:  # all
                    for t in types:
                        where.append(
                            "EXISTS (SELECT 1 FROM json_each(pokemons.types_json) je WHERE je.value = ?)"
                        )
                        params.append(t)
            else:
                if payload.type_mode == "any":
                    ors = []
                    for t in types:
                        ors.append('types_json LIKE ?')
                        params.append(f'%"{t}"%')
                    where.append("(" + " OR ".join(ors) + ")")
                else:
                    for t in types:
                        where.append('types_json LIKE ?')
                        params.append(f'%"{t}"%')

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    # Sorting
    candidate_sort = [
        "name",
        "dex_no",
        "hp",
        "attack", "atk",
        "defense", "def",
        "sp_attack", "sp_atk", "spa",
        "sp_defense", "sp_def", "spd",
        "speed", "spe",
        "bst", "total", "sum",
    ]
    allowed_sort = [c for c in candidate_sort if c in pcols]
    order_sql = _parse_sort(payload.sort, allowed_sort) if payload.sort else ""

    limit = max(0, int(payload.limit or 10))
    offset = max(0, int(payload.offset or 0))

    sql = f"SELECT {select_cols_sql} FROM pokemons{where_sql}{order_sql} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    items = execute_query(get_connection(), sql, params)
    return {"items": items, "limit": limit, "offset": offset}


# -----------------------------
# search_moves
# -----------------------------
def search_moves_handler(payload: SearchMovesInput) -> Dict[str, Any]:
    conn = get_connection()
    try:
        mcols = list(get_table_columns(conn, "moves"))
    finally:
        pass

    base_select_cols = [
        "id",
        "move_key",
        "name",
        "type",
        "category",
        "power",
        "activation_time",
        "startup_time",
        "startup_time_q",
        "startup_time_plus",
        "recovery_time",
        "total_time",
        "total_time_plus",
        "dps",
        "direct_attack",
        "finger_wag",
        "protect",
        "substitute",
        "range_",
        "effect",
        "page_url",
    ]
    select_cols = _select_existing_columns(base_select_cols, mcols)

    where: List[str] = []
    params: List[Any] = []

    if payload.name_like:
        where.append("name LIKE ?")
        params.append(build_like(payload.name_like))
    if payload.type:
        placeholders = ",".join(["?"] * len(payload.type))
        where.append(f"type IN ({placeholders})")
        params.extend(payload.type)
    if payload.category:
        placeholders = ",".join(["?"] * len(payload.category))
        where.append(f"category IN ({placeholders})")
        params.extend(payload.category)
    if payload.range_like:
        where.append("range_ LIKE ?")
        params.append(build_like(payload.range_like))

    # Flags exact matches
    if payload.direct_attack:
        where.append("direct_attack = ?")
        params.append(payload.direct_attack)
    if payload.finger_wag:
        where.append("finger_wag = ?")
        params.append(payload.finger_wag)
    if payload.protect:
        where.append("protect = ?")
        params.append(payload.protect)
    if payload.substitute:
        where.append("substitute = ?")
        params.append(payload.substitute)

    # Numeric ranges
    nranges: List[Tuple[str, Optional[float], Optional[float]]] = [
        ("power", payload.power_min, payload.power_max),
        ("activation_time", payload.activation_time_min, payload.activation_time_max),
        ("startup_time", payload.startup_time_min, payload.startup_time_max),
        ("startup_time_q", payload.startup_time_q_min, payload.startup_time_q_max),
        ("recovery_time", payload.recovery_time_min, payload.recovery_time_max),
        ("total_time", payload.total_time_min, payload.total_time_max),
        ("dps", payload.dps_min, payload.dps_max),
    ]
    for col, mn, mx in nranges:
        if mn is not None:
            where.append(f"{col} >= ?")
            params.append(mn)
        if mx is not None:
            where.append(f"{col} <= ?")
            params.append(mx)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    allowed_sort = [
        "name",
        "power",
        "activation_time",
        "startup_time",
        "startup_time_q",
        "recovery_time",
        "total_time",
        "dps",
    ]
    order_sql = _parse_sort(payload.sort, allowed_sort) if payload.sort else ""

    limit = max(0, int(payload.limit or 10))
    offset = max(0, int(payload.offset or 0))

    sql = f"SELECT {', '.join(select_cols)} FROM moves{where_sql}{order_sql} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    items = execute_query(get_connection(), sql, params)
    return {"items": items, "limit": limit, "offset": offset}


# -----------------------------
# get_pokemon_detail
# -----------------------------
def get_pokemon_detail_handler(payload: GetPokemonDetailInput) -> Dict[str, Any]:
    if not payload.id and not payload.name:
        raise ValueError("Either id or name is required")

    conn = get_connection()
    psel = "*"

    if payload.id:
        pokemon = execute_one(conn, f"SELECT {psel} FROM pokemons WHERE id = ?", [payload.id])
    else:
        pokemon = execute_one(conn, f"SELECT {psel} FROM pokemons WHERE name = ?", [payload.name])
    if not pokemon:
        raise HTTPException(status_code=404, detail="Pokemon not found")

    mcols = list(get_table_columns(conn, "moves"))
    msel_base = [
        "id",
        "move_key",
        "name",
        "type",
        "category",
        "power",
        "activation_time",
        "startup_time",
        "startup_time_q",
        "startup_time_plus",
        "recovery_time",
        "total_time",
        "total_time_plus",
        "dps",
        "direct_attack",
        "finger_wag",
        "protect",
        "substitute",
        "range_",
        "effect",
        "page_url",
    ]
    msel = ", ".join([f"m.{c}" for c in msel_base if c in mcols])

    sql = f"""
        SELECT pm.learn_method, pm.level, pm.tm_no, {msel}
        FROM pokemon_moves pm
        JOIN moves m ON m.id = pm.move_id
        WHERE pm.pokemon_id = ?
        ORDER BY m.name ASC
    """
    rows = execute_query(conn, sql, [pokemon["id"]])
    moves: List[Dict[str, Any]] = []
    for r in rows:
        learn = {
            "learn_method": r.get("learn_method"),
            "level": r.get("level"),
            "tm_no": r.get("tm_no"),
        }
        move = {k: v for k, v in r.items() if k not in ("learn_method", "level", "tm_no")}
        moves.append({"learn_method": learn["learn_method"], "level": learn["level"], "tm_no": learn["tm_no"], "move": move})

    return {"pokemon": pokemon, "moves": moves}


# -----------------------------
# get_move_detail
# -----------------------------
def get_move_detail_handler(payload: GetMoveDetailInput) -> Dict[str, Any]:
    if not payload.id and not payload.name:
        raise ValueError("Either id or name is required")

    conn = get_connection()
    mcols = list(get_table_columns(conn, "moves"))
    msel_base = [
        "id",
        "move_key",
        "name",
        "type",
        "category",
        "power",
        "activation_time",
        "startup_time",
        "startup_time_q",
        "startup_time_plus",
        "recovery_time",
        "total_time",
        "total_time_plus",
        "dps",
        "direct_attack",
        "finger_wag",
        "protect",
        "substitute",
        "range_",
        "effect",
        "page_url",
    ]
    msel = ", ".join([c for c in msel_base if c in mcols])

    if payload.id:
        move = execute_one(conn, f"SELECT {msel} FROM moves WHERE id = ?", [payload.id])
    else:
        move = execute_one(conn, f"SELECT {msel} FROM moves WHERE name = ?", [payload.name])
    if not move:
        raise HTTPException(status_code=404, detail="Move not found")

    # Select all pokemon columns to be schema-agnostic (e.g., atk/def/spa/spd/spe)
    psel = "p.*"

    sql = f"""
        SELECT pm.learn_method, pm.level, pm.tm_no, {psel}
        FROM pokemon_moves pm
        JOIN pokemons p ON p.id = pm.pokemon_id
        WHERE pm.move_id = ?
        ORDER BY p.name ASC
    """
    rows = execute_query(conn, sql, [move["id"]])
    pokemons: List[Dict[str, Any]] = []
    for r in rows:
        learn = {
            "learn_method": r.get("learn_method"),
            "level": r.get("level"),
            "tm_no": r.get("tm_no"),
        }
        pokemon = {k: v for k, v in r.items() if k not in ("learn_method", "level", "tm_no")}
        pokemons.append({"learn_method": learn["learn_method"], "level": learn["level"], "tm_no": learn["tm_no"], "pokemon": pokemon})

    return {"move": move, "pokemons": pokemons}


# -----------------------------
# Registration (MCP + REST)
# -----------------------------
def run_code_handler(payload: RunCodeInput) -> Dict[str, Any]:
    from src.code_environment import run_user_code_with_timeout
    out = run_user_code_with_timeout(
        code=payload.code,
        db_path=payload.db_path,
        args=payload.args or {},
        timeout_sec=10.0,
    )
    data = {"result": out.get("result"), "stdout": out.get("stdout", "")}
    if out.get("error"):
        data["error"] = out["error"]
    return data


def _load_prompt_text() -> str:
    try:
        base_dir = os.path.dirname(__file__)
        with open(os.path.join(base_dir, "prompt.txt"), "r", encoding="utf-8") as f:
            txt = f.read().strip()
            # Limit size to keep OpenAPI reasonable
            return txt[:8000]
    except Exception:
        return ""


RUN_CODE_LONG_DESC = _load_prompt_text()


def register_tools(app: FastAPI, mcp=None) -> None:
    router = APIRouter(prefix="/tools", tags=["tools"])

    # REST fallbacks
    @router.post(
        "/search_pokemons",
        operation_id="search_pokemons",
        name="search_pokemons",
        summary="Search Pokemons",
        description="ポケモンの検索。タイプ any/all、部分一致（name/obtain_method）、数値範囲、ソート、ページングに対応。",
        response_model=SearchPokemonsOutput,
        responses={
            200: {
                "description": "成功時のレスポンス",
                "content": {
                    "application/json": {
                        "example": {
                            "items": [
                                {"id": 6, "name": "ポカブ", "hp": 65}
                            ],
                            "limit": 10,
                            "offset": 0
                        }
                    }
                }
            }
        }
    )
    def search_pokemons_route(payload: SearchPokemonsInput):
        try:
            return search_pokemons_handler(payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post(
        "/search_moves",
        operation_id="search_moves",
        name="search_moves",
        summary="Search Moves",
        description="技の検索。タイプ/分類、部分一致（name/range）、各数値範囲、フラグ（接触/ゆびをふる/まもる/みがわり）、ソート、ページングに対応。",
        response_model=SearchMovesOutput,
        responses={
            200: {
                "description": "成功時のレスポンス",
                "content": {
                    "application/json": {
                        "example": {
                            "items": [
                                {"id": 123, "name": "マッハパンチ", "dps": 8.5}
                            ],
                            "limit": 10,
                            "offset": 0
                        }
                    }
                }
            }
        }
    )
    def search_moves_route(payload: SearchMovesInput):
        try:
            return search_moves_handler(payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post(
        "/get_pokemon_detail",
        operation_id="get_pokemon_detail",
        name="get_pokemon_detail",
        summary="Get Pokemon Detail",
        description="ポケモン詳細取得。ポケモン本体の情報に加えて、覚える技リスト（覚え方/レベル/tm_no 付き）を返します。",
        response_model=PokemonDetailOutput,
        responses={
            200: {
                "description": "成功時のレスポンス",
                "content": {
                    "application/json": {
                        "example": {
                            "pokemon": {"id": 6, "name": "ポカブ", "hp": 65},
                            "moves": [
                                {
                                    "learn_method": "レベル",
                                    "level": 15,
                                    "tm_no": -1,
                                    "move": {"id": 321, "name": "ニトロチャージ"}
                                }
                            ]
                        }
                    }
                }
            }
        }
    )
    def get_pokemon_detail_route(payload: GetPokemonDetailInput):
        try:
            return get_pokemon_detail_handler(payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post(
        "/get_move_detail",
        operation_id="get_move_detail",
        name="get_move_detail",
        summary="Get Move Detail",
        description="技詳細取得。技本体の情報に加えて、その技を覚えるポケモン一覧（覚え方/レベル/tm_no 付き）を返します。",
        response_model=MoveDetailOutput,
        responses={
            200: {
                "description": "成功時のレスポンス",
                "content": {
                    "application/json": {
                        "example": {
                            "move": {"id": 321, "name": "ニトロチャージ"},
                            "pokemons": [
                                {
                                    "learn_method": "レベル",
                                    "level": 15,
                                    "tm_no": -1,
                                    "pokemon": {"id": 6, "name": "ポカブ"}
                                }
                            ]
                        }
                    }
                }
            }
        }
    )
    def get_move_detail_route(payload: GetMoveDetailInput):
        try:
            return get_move_detail_handler(payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Add run_code REST route
    long_desc = "ユーザーコードを安全サンドボックスで実行。SQLite は read-only で、sql()/scalar() ヘルパが利用可能。結果は result 変数で返す。"
    if RUN_CODE_LONG_DESC:
        long_desc += "\n\n詳細: run_code 用プロンプト\n" + RUN_CODE_LONG_DESC

    @router.post(
        "/run_code",
        operation_id="run_code",
        name="run_code",
        summary="Run User Python Code (read-only DB)",
        description=long_desc,
        response_model=RunCodeOutput,
    )
    def run_code_route(payload: RunCodeInput):
        try:
            return run_code_handler(payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Include router after all routes (ensures run_code is visible)
    app.include_router(router)

    # MCP registration if available
    if mcp is None:
        return

    # Try modern registration API
    try:
        if hasattr(mcp, "register_tool"):
            mcp.register_tool(
                name="search_pokemons",
                input_model=SearchPokemonsInput,
                output_model=SearchPokemonsOutput,
                handler=search_pokemons_handler,
            )
            mcp.register_tool(
                name="search_moves",
                input_model=SearchMovesInput,
                output_model=SearchMovesOutput,
                handler=search_moves_handler,
            )
            mcp.register_tool(
                name="get_pokemon_detail",
                input_model=GetPokemonDetailInput,
                output_model=PokemonDetailOutput,
                handler=get_pokemon_detail_handler,
            )
            mcp.register_tool(
                name="get_move_detail",
                input_model=GetMoveDetailInput,
                output_model=MoveDetailOutput,
                handler=get_move_detail_handler,
            )
            mcp.register_tool(
                name="run_code",
                input_model=RunCodeInput,
                output_model=RunCodeOutput,
                handler=run_code_handler,
            )
            return
    except Exception:
        pass

    # Fallback to decorator-style API
    try:
        if hasattr(mcp, "tool"):
            mcp.tool(name="search_pokemons", input_model=SearchPokemonsInput, output_model=dict)(search_pokemons_handler)
            mcp.tool(name="search_moves", input_model=SearchMovesInput, output_model=dict)(search_moves_handler)
            mcp.tool(name="get_pokemon_detail", input_model=GetPokemonDetailInput, output_model=dict)(get_pokemon_detail_handler)
            mcp.tool(name="get_move_detail", input_model=GetMoveDetailInput, output_model=dict)(get_move_detail_handler)
            mcp.tool(name="run_code", input_model=RunCodeInput, output_model=RunCodeOutput)(run_code_handler)
            return
    except Exception:
        pass

    # If neither API is present, tools are still available via REST fallbacks.


