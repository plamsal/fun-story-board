"""Storage. Three tables, and every SQL query in the project.

    circles        a group of friends sharing one link
    contributions  one row per person per day (name, three words, optional sentence)
    stories        one story per circle per day (rewritten as friends join)

Two databases are supported with the same queries:

    SQLite    on your machine (a file in data/, nothing to install)
    Postgres  on the host, when DATABASE_URL is set (free hosts wipe local files)

The game rules never touch SQL; they only call the functions below.
"""

import json
import os
import sqlite3

from .config import settings

IS_POSTGRES = bool(settings.database_url)

if IS_POSTGRES:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    _pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=4,
        kwargs={"autocommit": True, "row_factory": dict_row},
        check=ConnectionPool.check_connection,  # replace connections the host closed
        open=True,
    )
else:
    if settings.db_path != ":memory:":
        os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    _conn = sqlite3.connect(settings.db_path, check_same_thread=False, isolation_level=None)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode = WAL")


def _all(sql: str, *args) -> list[dict]:
    """Run a query and return its rows. Queries are written with ? placeholders."""
    if IS_POSTGRES:
        with _pool.connection() as conn:
            cursor = conn.execute(sql.replace("?", "%s"), args)
            return cursor.fetchall() if cursor.description else []
    cursor = _conn.execute(sql, args)
    return [dict(row) for row in cursor.fetchall()]


def _one(sql: str, *args) -> dict | None:
    rows = _all(sql, *args)
    return rows[0] if rows else None


# ---------- tables ----------

_ID = "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

_TABLES = [
    """CREATE TABLE IF NOT EXISTS circles (
        id           TEXT PRIMARY KEY,
        name         TEXT NOT NULL,
        people_limit INTEGER NOT NULL,
        style        TEXT NOT NULL DEFAULT 'classic',
        created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    f"""CREATE TABLE IF NOT EXISTS contributions (
        id         {_ID},
        circle_id  TEXT NOT NULL REFERENCES circles(id),
        day        TEXT NOT NULL,              -- YYYY-MM-DD
        player_id  TEXT NOT NULL,              -- random id kept in a browser cookie
        name       TEXT NOT NULL,
        dream      TEXT NOT NULL,
        peace      TEXT NOT NULL,
        love       TEXT NOT NULL,
        sentence   TEXT NOT NULL DEFAULT '',   -- optional: one sentence in their own words
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (circle_id, day, player_id)
    )""",
    """CREATE TABLE IF NOT EXISTS stories (
        circle_id  TEXT NOT NULL REFERENCES circles(id),
        day        TEXT NOT NULL,
        title      TEXT NOT NULL,
        text       TEXT NOT NULL,              -- words as [[word]], names as {{Name}}
        closing    TEXT NOT NULL,              -- one thought to carry into the day
        people     INTEGER NOT NULL,           -- how many friends this version includes
        source     TEXT NOT NULL,              -- 'claude' or 'placeholder'
        style      TEXT NOT NULL DEFAULT 'classic',
        matches    TEXT NOT NULL DEFAULT '[]', -- JSON: [{"names": [a, b], "why": "..."}]
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (circle_id, day)
    )""",
]

# Columns added after the first version. Older databases get them on startup.
_ADDED_COLUMNS = [
    ("circles", "style", "TEXT NOT NULL DEFAULT 'classic'"),
    ("contributions", "sentence", "TEXT NOT NULL DEFAULT ''"),
    ("stories", "style", "TEXT NOT NULL DEFAULT 'classic'"),
    ("stories", "matches", "TEXT NOT NULL DEFAULT '[]'"),
]


def _column_names(table: str) -> set[str]:
    if IS_POSTGRES:
        rows = _all("SELECT column_name AS name FROM information_schema.columns WHERE table_name = ?", table)
    else:
        rows = _all(f"PRAGMA table_info({table})")
    return {row["name"] for row in rows}


def create_tables() -> None:
    for statement in _TABLES:
        _all(statement)
    for table, column, definition in _ADDED_COLUMNS:
        if column not in _column_names(table):
            _all(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


create_tables()


# ---------- circles ----------

def insert_circle(circle_id: str, name: str, people_limit: int, style: str = "classic") -> None:
    _all("INSERT INTO circles (id, name, people_limit, style) VALUES (?, ?, ?, ?)",
         circle_id, name, people_limit, style)


def get_circle(circle_id: str) -> dict | None:
    return _one("SELECT id, name, people_limit, style FROM circles WHERE id = ?", circle_id)


# ---------- contributions ----------

def insert_contribution(circle_id, day, player_id, name, dream, peace, love, sentence="") -> None:
    _all(
        """INSERT INTO contributions (circle_id, day, player_id, name, dream, peace, love, sentence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        circle_id, day, player_id, name, dream, peace, love, sentence,
    )


def count_people(circle_id: str, day: str) -> int:
    return _one("SELECT COUNT(*) AS n FROM contributions WHERE circle_id = ? AND day = ?",
                circle_id, day)["n"]


def list_contributions(circle_id: str, day: str) -> list[dict]:
    """Everyone's words for a day, in the order they were added."""
    return _all(
        """SELECT name, dream, peace, love, sentence FROM contributions
           WHERE circle_id = ? AND day = ? ORDER BY id""",
        circle_id, day,
    )


def get_contribution(circle_id: str, day: str, player_id: str) -> dict | None:
    """One player's words, plus `position`: 1 for the first friend of the day, etc."""
    return _one(
        """SELECT c.name, c.dream, c.peace, c.love, c.sentence,
                  (SELECT COUNT(*) FROM contributions e
                    WHERE e.circle_id = c.circle_id AND e.day = c.day AND e.id <= c.id) AS position
           FROM contributions c
           WHERE c.circle_id = ? AND c.day = ? AND c.player_id = ?""",
        circle_id, day, player_id,
    )


# ---------- stories ----------

def save_story(circle_id, day, title, text, closing, people, source, style, matches) -> None:
    _all(
        """INSERT INTO stories (circle_id, day, title, text, closing, people, source, style, matches)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (circle_id, day) DO UPDATE SET
               title = excluded.title, text = excluded.text, closing = excluded.closing,
               people = excluded.people, source = excluded.source, style = excluded.style,
               matches = excluded.matches, updated_at = CURRENT_TIMESTAMP""",
        circle_id, day, title, text, closing, people, source, style, json.dumps(matches),
    )


def _with_matches(story: dict | None) -> dict | None:
    if story:
        story["matches"] = json.loads(story["matches"] or "[]")
    return story


def get_story(circle_id: str, day: str) -> dict | None:
    return _with_matches(_one(
        """SELECT day, title, text, closing, people, source, style, matches
           FROM stories WHERE circle_id = ? AND day = ?""",
        circle_id, day,
    ))


def get_latest_story(circle_id: str) -> dict | None:
    return _with_matches(_one(
        """SELECT day, title, text, closing, people, source, style, matches
           FROM stories WHERE circle_id = ? ORDER BY day DESC LIMIT 1""",
        circle_id,
    ))


def list_stories(circle_id: str, before_day: str) -> list[dict]:
    """Finished days, newest first."""
    return _all(
        """SELECT day, title, text, people, style FROM stories
           WHERE circle_id = ? AND day < ? ORDER BY day DESC""",
        circle_id, before_day,
    )


def list_days_needing_story(circle_id: str) -> list[str]:
    """Days where friends added words that the saved story does not include yet."""
    rows = _all(
        """SELECT c.day AS day FROM contributions c
           LEFT JOIN stories s ON s.circle_id = c.circle_id AND s.day = c.day
           WHERE c.circle_id = ?
           GROUP BY c.day
           HAVING COUNT(*) > COALESCE(MAX(s.people), 0)""",
        circle_id,
    )
    return [row["day"] for row in rows]
