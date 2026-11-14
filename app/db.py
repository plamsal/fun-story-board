"""Storage. One SQLite file, three tables.

    circles        a group of friends sharing one link
    contributions  one row per person per day (name + three words)
    stories        one story per circle per day (rewritten as friends join)

All SQL lives in this file, so the storage can be swapped later
(for example to Postgres) without touching the game rules.
"""

import os
import sqlite3

from .config import settings

if settings.db_path != ":memory:":
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)

conn = sqlite3.connect(settings.db_path, check_same_thread=False, isolation_level=None)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode = WAL")

conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS circles (
        id           TEXT PRIMARY KEY,
        name         TEXT NOT NULL,
        people_limit INTEGER NOT NULL,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS contributions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        circle_id  TEXT NOT NULL REFERENCES circles(id),
        day        TEXT NOT NULL,           -- YYYY-MM-DD
        player_id  TEXT NOT NULL,           -- random id kept in a browser cookie
        name       TEXT NOT NULL,
        dream      TEXT NOT NULL,
        peace      TEXT NOT NULL,
        love       TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (circle_id, day, player_id)
    );

    CREATE TABLE IF NOT EXISTS stories (
        circle_id  TEXT NOT NULL REFERENCES circles(id),
        day        TEXT NOT NULL,
        title      TEXT NOT NULL,
        text       TEXT NOT NULL,           -- words as [[word]], names as {{Name}}
        closing    TEXT NOT NULL,           -- one thought to carry into the day
        people     INTEGER NOT NULL,        -- how many friends this version includes
        source     TEXT NOT NULL,           -- 'claude' or 'placeholder'
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (circle_id, day)
    );
    """
)


def _one(sql: str, *args) -> dict | None:
    row = conn.execute(sql, args).fetchone()
    return dict(row) if row else None


def _all(sql: str, *args) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, args).fetchall()]


# ---- circles ----

def insert_circle(circle_id: str, name: str, people_limit: int) -> None:
    conn.execute(
        "INSERT INTO circles (id, name, people_limit) VALUES (?, ?, ?)",
        (circle_id, name, people_limit),
    )


def get_circle(circle_id: str) -> dict | None:
    return _one("SELECT * FROM circles WHERE id = ?", circle_id)


# ---- contributions ----

def insert_contribution(circle_id, day, player_id, name, dream, peace, love) -> None:
    conn.execute(
        """INSERT INTO contributions (circle_id, day, player_id, name, dream, peace, love)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (circle_id, day, player_id, name, dream, peace, love),
    )


def count_people(circle_id: str, day: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM contributions WHERE circle_id = ? AND day = ?",
        (circle_id, day),
    ).fetchone()[0]


def list_contributions(circle_id: str, day: str) -> list[dict]:
    """Everyone's words for a day, in the order they were added."""
    return _all(
        """SELECT name, dream, peace, love FROM contributions
           WHERE circle_id = ? AND day = ? ORDER BY id""",
        circle_id, day,
    )


def get_contribution(circle_id: str, day: str, player_id: str) -> dict | None:
    """One player's words, plus `position`: 1 for the first friend of the day, etc."""
    return _one(
        """SELECT c.name, c.dream, c.peace, c.love,
                  (SELECT COUNT(*) FROM contributions e
                    WHERE e.circle_id = c.circle_id AND e.day = c.day AND e.id <= c.id) AS position
           FROM contributions c
           WHERE c.circle_id = ? AND c.day = ? AND c.player_id = ?""",
        circle_id, day, player_id,
    )


# ---- stories ----

def save_story(circle_id, day, title, text, closing, people, source) -> None:
    conn.execute(
        """INSERT INTO stories (circle_id, day, title, text, closing, people, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (circle_id, day) DO UPDATE SET
               title = excluded.title, text = excluded.text, closing = excluded.closing,
               people = excluded.people, source = excluded.source,
               updated_at = datetime('now')""",
        (circle_id, day, title, text, closing, people, source),
    )


def get_story(circle_id: str, day: str) -> dict | None:
    return _one("SELECT * FROM stories WHERE circle_id = ? AND day = ?", circle_id, day)


def list_stories(circle_id: str, before_day: str) -> list[dict]:
    """Finished days, newest first."""
    return _all(
        """SELECT day, title, text, people FROM stories
           WHERE circle_id = ? AND day < ? ORDER BY day DESC""",
        circle_id, before_day,
    )


def list_days_needing_story(circle_id: str) -> list[str]:
    """Days where friends added words that the saved story does not include yet."""
    rows = _all(
        """SELECT c.day FROM contributions c
           LEFT JOIN stories s ON s.circle_id = c.circle_id AND s.day = c.day
           WHERE c.circle_id = ?
           GROUP BY c.day
           HAVING COUNT(*) > COALESCE(MAX(s.people), 0)""",
        circle_id,
    )
    return [row["day"] for row in rows]
