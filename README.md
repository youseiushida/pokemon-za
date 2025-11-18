# Pokemon ZA scraper (local lists.html -> SQLite)

This script builds a SQLite database for Pokemon ZA:

- Reads local `lists.html` to get Pokemon basic data and detail page slugs
- Scrapes each Pokemon page (as in `pokemon.html`) to collect level/TM learnsets
- Scrapes each move page (as in `waza.html`) to collect detailed move info

## Requirements

```bash
pip install -r requirements.txt
```

## Usage

```bash
python scrape_za.py --lists lists.html --db za.sqlite3 --limit 0 --delay 0.8
```

- `--lists`: path to the provided `lists.html`
- `--db`: output SQLite file (created if not exists)
- `--limit`: limit number of Pokemon to scrape (0 = all from the list)
- `--delay`: delay between HTTP requests in seconds (be polite)

The database will contain three tables:

- `pokemons`: 図鑑番号、名前、タイプ、入手方法、種族値(HP/こうげき/ぼうぎょ/とくこう/とくぼう/すばやさ)、合計、ページ情報
- `moves`: 技の基本情報とフラグ、発動・発生・硬直時間、DPS、範囲・効果など
- `pokemon_moves`: ポケモンと技のリレーション、覚え方(レベル/技マシン/基本)、レベル、技マシン番号

Notes:
- HTML構造の変更があるとパーサが失敗する可能性があります。
- 外部サイトへアクセスします。リクエスト間のディレイを調整してください。


