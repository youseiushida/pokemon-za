#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudscraper-backed scraper (no edits to src.scrape_za).
Fetches HTML via Cloudflare-aware session and reuses existing parsers/DB helpers.

Usage:
  uv run -m src.scrape_za_cloud --lists lists.html --db za.sqlite3 --limit 5 --delay 0.3
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from typing import Dict, List, Optional, Tuple, Set

try:
    import cloudscraper  # type: ignore
except Exception as e:
    cloudscraper = None  # type: ignore

from bs4 import BeautifulSoup, UnicodeDammit

# Reuse everything from the existing scraper
from src.scrape_za import (
    POKEMON_BASE,
    MOVE_SEARCH_BASE,
    ensure_eucjp,
    parse_lists_html,
    parse_pokemon_moves_from_soup,
    parse_move_detail_from_html,
    init_db,
    upsert_pokemon,
    upsert_move,
    upsert_pokemon_move,
)


def merge_move_duplicates_by_name(conn: sqlite3.Connection, canonical_move_id: int, name: str) -> None:
    """Merge duplicate move rows that share the same name into the canonical row.
    - Migrates pokemon_moves relations to the canonical move_id with INSERT OR IGNORE
    - Deletes duplicate move rows afterwards
    """
    cur = conn.cursor()
    cur.execute("SELECT id FROM moves WHERE name=? AND id<>?", (name, canonical_move_id))
    duplicates = [int(r[0]) for r in cur.fetchall()]
    if not duplicates:
        return

    for dup_id in duplicates:
        # Migrate relations
        cur.execute("SELECT pokemon_id, learn_method, level, tm_no FROM pokemon_moves WHERE move_id=?", (dup_id,))
        for pokemon_id, learn_method, level, tm_no in cur.fetchall():
            cur.execute(
                """
                INSERT OR IGNORE INTO pokemon_moves (pokemon_id, move_id, learn_method, level, tm_no)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pokemon_id, canonical_move_id, learn_method, level, tm_no),
            )
        # Remove old relations and duplicate move row
        cur.execute("DELETE FROM pokemon_moves WHERE move_id=?", (dup_id,))
        cur.execute("DELETE FROM moves WHERE id=?", (dup_id,))
    conn.commit()


def update_move_record_cloud(conn: sqlite3.Connection, move_id: int, data: Dict) -> None:
    """Safe move update that resolves name-uniqueness conflicts by merging duplicates first."""
    cur = conn.cursor()

    # Discover existing columns to avoid OperationalError against older DBs
    cur.execute("PRAGMA table_info(moves)")
    existing_cols = {row[1] for row in cur.fetchall()}

    # Normalize incoming keys to match DB columns
    normalized: Dict[str, Optional[str]] = {}
    normalized["name"] = data.get("name")
    normalized["type"] = data.get("type")
    normalized["category"] = data.get("category")
    normalized["power"] = data.get("power")
    normalized["activation_time"] = data.get("activation_time")
    normalized["startup_time"] = data.get("startup_time")
    # accept both keys for quickclaw
    normalized["startup_time_q"] = data.get("startup_time_q")
    if normalized["startup_time_q"] is None:
        normalized["startup_time_q"] = data.get("startup_time_quickclaw")
    normalized["startup_time_plus"] = data.get("startup_time_plus")
    normalized["recovery_time"] = data.get("recovery_time")
    normalized["total_time"] = data.get("total_time")
    normalized["total_time_plus"] = data.get("total_time_plus")
    normalized["dps"] = data.get("dps")
    # flags: accept both naming schemes
    normalized["direct_attack"] = data.get("direct_attack")
    if normalized["direct_attack"] is None:
        normalized["direct_attack"] = data.get("contact")
    normalized["finger_wag"] = data.get("finger_wag")
    if normalized["finger_wag"] is None:
        normalized["finger_wag"] = data.get("finger")
    normalized["protect"] = data.get("protect")
    normalized["substitute"] = data.get("substitute")
    # range: accept both names
    normalized["range_"] = data.get("range_")
    if normalized["range_"] is None:
        normalized["range_"] = data.get("range")
    normalized["effect"] = data.get("effect")
    normalized["page_url"] = data.get("page_url")

    # Fallbacks: if plus values are missing, mirror base values
    if normalized.get("startup_time_plus") is None:
        normalized["startup_time_plus"] = normalized.get("startup_time")
    if normalized.get("total_time_plus") is None:
        normalized["total_time_plus"] = normalized.get("total_time")

    # Map incoming data keys to column names
    mapping = [
        ("name", "name"),
        ("type", "type"),
        ("category", "category"),
        ("power", "power"),
        ("activation_time", "activation_time"),
        ("startup_time", "startup_time"),
        ("startup_time_q", "startup_time_q"),
        # legacy alias for quickclaw
        ("startup_time_q", "startup_time_quickclaw"),
        ("startup_time_plus", "startup_time_plus"),
        ("recovery_time", "recovery_time"),
        ("total_time", "total_time"),
        ("total_time_plus", "total_time_plus"),
        ("dps", "dps"),
        ("direct_attack", "direct_attack"),
        # legacy alias for contact
        ("direct_attack", "contact"),
        ("finger_wag", "finger_wag"),
        # legacy alias for finger
        ("finger_wag", "finger"),
        ("protect", "protect"),
        ("substitute", "substitute"),
        ("range_", "range_"),
        # legacy alias for range
        ("range_", "range"),
        ("effect", "effect"),
        ("page_url", "page_url"),
    ]

    set_parts = []
    values: list = []
    for key, col in mapping:
        if col in existing_cols:
            set_parts.append(f"{col}=?")
            values.append(normalized.get(key))

    if not set_parts:
        return  # nothing to update

    values.append(move_id)
    sql = f"UPDATE moves SET {', '.join(set_parts)} WHERE id=?"

    def do_update() -> None:
        cur.execute(sql, tuple(values))
        conn.commit()

    try:
        do_update()
        return
    except sqlite3.IntegrityError:
        # Merge duplicates and retry
        if data.get("name"):
            merge_move_duplicates_by_name(conn, move_id, data["name"])
        do_update()


def migrate_moves_schema(conn: sqlite3.Connection) -> None:
    """Ensure the 'moves' table has all expected columns; add missing ones if needed."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(moves)")
    existing_cols = {row[1] for row in cur.fetchall()}

    # Column name -> SQL type
    expected = {
        "move_key": "INTEGER",
        "name": "TEXT",
        "type": "TEXT",
        "category": "TEXT",
        "power": "INTEGER",
        "activation_time": "REAL",
        "startup_time": "REAL",
        "startup_time_q": "REAL",
        "startup_time_plus": "REAL",
        "recovery_time": "REAL",
        "total_time": "REAL",
        "total_time_plus": "REAL",
        "dps": "REAL",
        "direct_attack": "TEXT",
        "finger_wag": "TEXT",
        "protect": "TEXT",
        "substitute": "TEXT",
        "range_": "TEXT",
        "effect": "TEXT",
        "page_url": "TEXT",
    }

    for col, coltype in expected.items():
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE moves ADD COLUMN {col} {coltype}")
    conn.commit()

def get_cloudscraper_session():
    if cloudscraper is None:
        raise RuntimeError("cloudscraper is not installed. Run: uv pip install cloudscraper")
    # browser='chrome' and mobile/desktop can be tuned; use desktop default
    sess = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "desktop": True,
        }
    )
    # Friendly headers
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
        "Referer": POKEMON_BASE,
    })
    return sess


def cloud_fetch_html(session, url: str) -> str:
    resp = session.get(url, timeout=30, allow_redirects=True)
    # Robust decode using bs4.UnicodeDammit to avoid mojibake across UTF-8/EUC-JP/SJIS
    data = resp.content
    ud = UnicodeDammit(data, is_html=True)
    return ud.unicode_markup or data.decode("utf-8", errors="ignore")


def fetch_html_with_playwright_cloud(url: str) -> Optional[str]:
    """Fallback HTML fetch using Playwright for move detail pages."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
                extra_http_headers={
                    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
                },
                viewport={"width": 1366, "height": 900},
                bypass_csp=True,
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait for either 技データ or 効果テーブル to appear
            for _ in range(20):
                if page.locator('table[summary*="技データ"], table.effect_table').count() > 0:
                    break
                page.wait_for_timeout(1000)
            html = page.content()
            context.close()
            browser.close()
            return html
    except Exception:
        return None


def scrape_pokemon_moves_cloud(session, url: str) -> List[Dict]:
    # Try as-is
    html = cloud_fetch_html(session, url)
    soup = BeautifulSoup(html, "lxml")
    moves = parse_pokemon_moves_from_soup(soup)
    if moves:
        return moves
    # Try view=pc variant
    url_pc = url + ("&view=pc" if "?" in url else "?view=pc")
    html = cloud_fetch_html(session, url_pc)
    soup = BeautifulSoup(html, "lxml")
    moves = parse_pokemon_moves_from_soup(soup)
    return moves


def scrape_move_detail_cloud(session, move_key: int) -> Dict:
    url = f"{MOVE_SEARCH_BASE}{move_key}"
    html = cloud_fetch_html(session, url)
    soup = BeautifulSoup(html, "lxml")
    data = parse_move_detail_from_html(soup)
    # If critical fields missing, try view=pc
    critical_missing = not data or any(
        data.get(k) in (None, "", "-")
        for k in ("type", "category", "power", "activation_time", "range_", "direct_attack", "finger_wag", "protect", "substitute")
    )
    if critical_missing:
        # try view=pc
        url_pc = url + "&view=pc"
        html = cloud_fetch_html(session, url_pc)
        soup = BeautifulSoup(html, "lxml")
        data = parse_move_detail_from_html(soup)
        critical_missing = not data or any(
            data.get(k) in (None, "", "-")
            for k in ("type", "category", "power", "activation_time", "range_", "direct_attack", "finger_wag", "protect", "substitute")
        )
        if data and not critical_missing:
            url = url_pc

    # Final fallback: Playwright
    if not data or critical_missing:
        html = fetch_html_with_playwright_cloud(url)
        if not html:
            url_pc = url + "&view=pc"
            html = fetch_html_with_playwright_cloud(url_pc)
            if html:
                url = url_pc
        if html:
            soup = BeautifulSoup(html, "lxml")
            data = parse_move_detail_from_html(soup)

    data["page_url"] = url
    data["move_key"] = move_key
    return data


def scrape_move_detail_by_url_cloud(session, url: str) -> Dict:
    html = cloud_fetch_html(session, url)
    soup = BeautifulSoup(html, "lxml")
    data = parse_move_detail_from_html(soup)
    critical_missing = not data or any(
        data.get(k) in (None, "", "-")
        for k in ("type", "category", "power", "activation_time", "range_", "direct_attack", "finger_wag", "protect", "substitute")
    )
    if critical_missing:
        if "view=pc" not in url:
            url_pc = url + ("&view=pc" if "?" in url else "?view=pc")
            html = cloud_fetch_html(session, url_pc)
            soup = BeautifulSoup(html, "lxml")
            data = parse_move_detail_from_html(soup)
            critical_missing = not data or any(
                data.get(k) in (None, "", "-")
                for k in ("type", "category", "power", "activation_time", "range_", "direct_attack", "finger_wag", "protect", "substitute")
            )
            if data and not critical_missing:
                url = url_pc
    # Final fallback: Playwright
    if not data or critical_missing:
        html = fetch_html_with_playwright_cloud(url)
        if not html and "view=pc" not in url:
            url_pc = url + ("&view=pc" if "?" in url else "?view=pc")
            html = fetch_html_with_playwright_cloud(url_pc)
            if html:
                url = url_pc
        if html:
            soup = BeautifulSoup(html, "lxml")
            data = parse_move_detail_from_html(soup)
    data["page_url"] = url
    data["move_key"] = None
    return data


def run(args) -> None:
    session = get_cloudscraper_session()

    # Prepare DB
    conn = sqlite3.connect(args.db)
    init_db(conn)
    # Make sure legacy DBs have the latest columns to receive move details
    migrate_moves_schema(conn)

    # Parse list page (local file path)
    pokemons = parse_lists_html(args.lists)
    if args.limit and args.limit > 0:
        pokemons = pokemons[: args.limit]
    print(f"Parsed {len(pokemons)} pokemons from {args.lists}")

    # Upsert pokemons first, collect mapping slug -> id
    slug_to_id: Dict[str, int] = {}
    for p in pokemons:
        pid = upsert_pokemon(conn, p)  # assumes scrape_za.upsert_pokemon signature accepts dict
        slug_to_id[p["slug"]] = pid

    seen_move_keys: Set[int] = set()
    seen_move_urls: Set[str] = set()

    # Learnsets
    for idx, p in enumerate(pokemons, start=1):
        pid = slug_to_id[p["slug"]]
        print(f"[{idx}/{len(pokemons)}] Scraping moves: {p['name']} ({p['page_url']})")
        try:
            move_entries = scrape_pokemon_moves_cloud(session, p["page_url"])
        except Exception as e:
            print(f"  ! Failed moves for {p['page_url']}: {e}", file=sys.stderr)
            time.sleep(args.delay)
            continue

        for me in move_entries:
            move_key = me.get("move_key")
            name = me.get("name") or ""
            page_url = f"{MOVE_SEARCH_BASE}{move_key}" if move_key else me.get("detail_url")
            mid = upsert_move(conn, move_key, name, page_url)
            upsert_pokemon_move(conn, pid, mid, me["method"], me["level"], me["tm_no"])
            if move_key:
                seen_move_keys.add(move_key)
            elif page_url:
                seen_move_urls.add(page_url)
        time.sleep(args.delay)

    # Move details (by id)
    print(f"Scraping move details for {len(seen_move_keys)} unique moves by id")
    for i, mk in enumerate(sorted(seen_move_keys), start=1):
        print(f"  [{i}/{len(seen_move_keys)}] move_key={mk} fetching detail ...")
        try:
            md = scrape_move_detail_cloud(session, mk)
        except Exception as e:
            print(f"  ! Failed move {mk}: {e}", file=sys.stderr)
            time.sleep(args.delay)
            continue
        cur = conn.cursor()
        cur.execute("SELECT id FROM moves WHERE move_key=?", (mk,))
        row = cur.fetchone()
        if row:
            move_row_id = int(row[0])
            update_move_record_cloud(conn, move_row_id, md)
            print(f"    -> ok name='{md.get('name')}' type='{md.get('type')}' url={md.get('page_url')}")
            if getattr(args, "debug", False):
                # Verify persisted key fields
                cur.execute("""
                    SELECT startup_time, startup_time_q, startup_time_plus,
                           recovery_time, total_time, total_time_plus, dps,
                           direct_attack, finger_wag, protect, substitute, range_, effect
                    FROM moves WHERE id=?
                """, (move_row_id,))
                persisted = cur.fetchone()
                if persisted:
                    st, stq, stp, rt, tt, ttp, dps, da, fw, pr, sb, rg, ef = persisted
                    print(f"       saved: startup={st} quickclaw={stq} plus={stp} rec={rt} total={tt} total_plus={ttp} dps={dps}")
                    print(f"              flags: 接触='{da}' 指='{fw}' 守='{pr}' 身代='{sb}' 範囲='{rg}'")
            if getattr(args, "debug", False) and i <= 3:
                # Save fetched HTML snapshot for verification
                try:
                    import os
                    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_live_snaps")
                    os.makedirs(out_dir, exist_ok=True)
                    # Re-fetch with cloudscraper to capture the final URL variant
                    html_dbg = cloud_fetch_html(session, md["page_url"])
                    with open(os.path.join(out_dir, f"cloud_move_{mk}.html"), "w", encoding="utf-8") as f:
                        f.write(html_dbg)
                except Exception:
                    pass
        if i % 25 == 0:
            print(f"  ... {i}/{len(seen_move_keys)}")
        time.sleep(args.delay)

    # Move details (by URL)
    if seen_move_urls:
        print(f"Scraping move details for {len(seen_move_urls)} unique moves by URL")
    for j, mu in enumerate(sorted(seen_move_urls), start=1):
        print(f"  [{j}/{len(seen_move_urls)}] url={mu} fetching detail ...")
        try:
            md = scrape_move_detail_by_url_cloud(session, mu)
        except Exception as e:
            print(f"  ! Failed move URL {mu}: {e}", file=sys.stderr)
            time.sleep(args.delay)
            continue
        cur = conn.cursor()
        cur.execute("SELECT id FROM moves WHERE page_url=?", (mu,))
        row = cur.fetchone()
        if row:
            update_move_record_cloud(conn, int(row[0]), md)
            print(f"    -> ok name='{md.get('name')}' type='{md.get('type')}' url={md.get('page_url')}")
        if j % 25 == 0:
            print(f"  ... {j}/{len(seen_move_urls)}")
        time.sleep(args.delay)

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ZA SQLite using cloudscraper (no edits to scrape_za)")
    parser.add_argument("--lists", required=True, help="Path to lists.html (local)")
    parser.add_argument("--db", required=True, help="Output SQLite path")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of pokemons (0 = all)")
    parser.add_argument("--delay", type=float, default=0.6, help="Delay between requests (seconds)")
    parser.add_argument("--debug", action="store_true", help="Save a few move detail HTML snapshots for verification")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()


