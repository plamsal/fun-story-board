"""Storage. Three tables, and every SQL query in the project.

    circles        a group of friends sharing one link
    contributions  one row per person per day (name, optional message to the circle)
    answers        one row per answer: which contribution, which question, the text
    stories        one story per circle per day (rewritten as friends join)

Answers have their own table so the questions can change over time without
changing the database: every answer remembers which question it answered.

Two databases are supported with the same queries:

    SQLite    on your machine (a file in data/, nothing to install)
    Postgres  on the host, when DATABASE_URL is set (free hosts wipe local files)

The game rules never touch SQL; they only call the functions below.
"""

import json
import os
import secrets
import sqlite3

from .config import settings
from .questions import in_order

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
    """CREATE TABLE IF NOT EXISTS circle_members (
        circle_id TEXT NOT NULL REFERENCES circles(id),
        player_id TEXT NOT NULL,
        PRIMARY KEY (circle_id, player_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS contributions (
        id         {_ID},
        circle_id  TEXT NOT NULL REFERENCES circles(id),
        day        TEXT NOT NULL,              -- YYYY-MM-DD
        player_id  TEXT NOT NULL,              -- random id kept in a browser cookie
        name       TEXT NOT NULL,
        sentence   TEXT NOT NULL DEFAULT '',   -- optional: their message to the circle (the quote)
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (circle_id, day, player_id)
    )""",
    """CREATE TABLE IF NOT EXISTS answers (
        contribution_id BIGINT NOT NULL REFERENCES contributions(id),
        question        TEXT NOT NULL,         -- question key, e.g. 'hope' (see questions.py)
        text            TEXT NOT NULL,
        PRIMARY KEY (contribution_id, question)
    )""",
    """CREATE TABLE IF NOT EXISTS stories (
        circle_id  TEXT NOT NULL REFERENCES circles(id),
        day        TEXT NOT NULL,
        title      TEXT NOT NULL,
        text       TEXT NOT NULL,              -- answers as [[3|words]], names as {{Name}}
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
    ("circles", "invite_token", "TEXT NOT NULL DEFAULT ''"),
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


def _move_old_answers() -> None:
    """The first version kept answers in three columns (dream, peace, love).
    Copy them into the answers table, then remove the old columns."""
    old = [c for c in ("dream", "peace", "love") if c in _column_names("contributions")]
    for column in old:
        _all(f"""INSERT INTO answers (contribution_id, question, text)
                 SELECT id, '{column}', {column} FROM contributions WHERE {column} <> ''
                 ON CONFLICT (contribution_id, question) DO NOTHING""")
    for column in old:
        _all(f"ALTER TABLE contributions DROP COLUMN {column}")


def create_tables() -> None:
    for statement in _TABLES:
        _all(statement)
    for table, column, definition in _ADDED_COLUMNS:
        if column not in _column_names(table):
            _all(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    _move_old_answers()
    for row in _all("SELECT id FROM circles WHERE invite_token = ''"):
        _all("UPDATE circles SET invite_token = ? WHERE id = ? AND invite_token = ''",
             secrets.token_urlsafe(32), row["id"])
    _all("""INSERT INTO circle_members (circle_id, player_id)
            SELECT DISTINCT circle_id, player_id FROM contributions WHERE 1 = 1
            ON CONFLICT (circle_id, player_id) DO NOTHING""")


create_tables()


# ---------- circles ----------

def insert_circle(circle_id: str, name: str, people_limit: int, style: str = "classic") -> None:
    _all("INSERT INTO circles (id, name, people_limit, style, invite_token) VALUES (?, ?, ?, ?, ?)",
         circle_id, name, people_limit, style, secrets.token_urlsafe(32))


def get_circle(circle_id: str) -> dict | None:
    return _one("SELECT id, name, people_limit, style, invite_token FROM circles WHERE id = ?", circle_id)


def list_circles(circle_ids: list[str], day: str, player_id: str) -> list[dict]:
    """Circles for the "Your circles" list: how many friends are in today, and whether you are."""
    if not circle_ids:
        return []
    marks = ", ".join("?" for _ in circle_ids)
    return _all(
        f"""SELECT c.id, c.name, c.people_limit, c.style,
                   (SELECT COUNT(*) FROM contributions x
                     WHERE x.circle_id = c.id AND x.day = ?) AS people,
                   (SELECT COUNT(*) FROM contributions x
                     WHERE x.circle_id = c.id AND x.day = ? AND x.player_id = ?) AS mine
            FROM circles c WHERE c.id IN ({marks})""",
        day, day, player_id, *circle_ids,
    )


# ---------- contributions and their answers ----------

def insert_contribution(circle_id, day, player_id, name, answers: dict[str, str], sentence="") -> None:
    """Save one friend's entry: their name, their answers by question key, their message."""
    row = _one(
        """INSERT INTO contributions (circle_id, day, player_id, name, sentence)
           VALUES (?, ?, ?, ?, ?) RETURNING id""",
        circle_id, day, player_id, name, sentence,
    )
    for question, text in answers.items():
        _all("INSERT INTO answers (contribution_id, question, text) VALUES (?, ?, ?)",
             row["id"], question, text)


def count_people(circle_id: str, day: str) -> int:
    return _one("SELECT COUNT(*) AS n FROM contributions WHERE circle_id = ? AND day = ?",
                circle_id, day)["n"]


def _with_answers(contributions: list[dict]) -> list[dict]:
    """Attach {"answers": {question: text}} to each contribution and drop the row id."""
    if not contributions:
        return []
    marks = ", ".join("?" for _ in contributions)
    rows = _all(f"SELECT contribution_id, question, text FROM answers WHERE contribution_id IN ({marks})",
                *(c["id"] for c in contributions))
    by_id: dict[int, dict] = {}
    for row in rows:
        by_id.setdefault(row["contribution_id"], {})[row["question"]] = row["text"]
    return [{**{k: v for k, v in c.items() if k != "id"}, "answers": in_order(by_id.get(c["id"], {}))}
            for c in contributions]


def list_contributions(circle_id: str, day: str) -> list[dict]:
    """Everyone's entry for a day, in the order they were added.
    Each is {"name", "sentence", "answers": {question: text}}."""
    return _with_answers(_all(
        """SELECT id, name, sentence FROM contributions
           WHERE circle_id = ? AND day = ? ORDER BY id""",
        circle_id, day,
    ))


def get_contribution(circle_id: str, day: str, player_id: str) -> dict | None:
    """One player's entry, plus `position`: 1 for the first friend of the day, etc."""
    found = _with_answers(_all(
        """SELECT c.id, c.name, c.sentence,
                  (SELECT COUNT(*) FROM contributions e
                    WHERE e.circle_id = c.circle_id AND e.day = c.day AND e.id <= c.id) AS position
           FROM contributions c
           WHERE c.circle_id = ? AND c.day = ? AND c.player_id = ?""",
        circle_id, day, player_id,
    ))
    return found[0] if found else None


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


def list_stories(circle_id: str, up_to_day: str) -> list[dict]:
    """Stories up to and including a day, newest first."""
    return _all(
        """SELECT day, title, text, people, style FROM stories
           WHERE circle_id = ? AND day <= ? ORDER BY day DESC""",
        circle_id, up_to_day,
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


# ---------- admin (see admin.py) ----------

def admin_totals() -> dict:
    return _one(
        """SELECT (SELECT COUNT(*) FROM circles) AS circles,
                  (SELECT COUNT(*) FROM contributions) AS entries,
                  (SELECT COUNT(*) FROM answers) AS answers,
                  (SELECT COUNT(*) FROM stories) AS stories"""
    )


def admin_circles() -> list[dict]:
    """Every circle with how much it has been used, most recently active first."""
    return _all(
        """SELECT c.id, c.name, c.style, c.people_limit,
                  COUNT(x.id) AS entries,
                  COUNT(DISTINCT x.day) AS days,
                  COUNT(DISTINCT x.player_id) AS people,
                  MAX(x.day) AS last_day
           FROM circles c LEFT JOIN contributions x ON x.circle_id = c.id
           GROUP BY c.id, c.name, c.style, c.people_limit
           ORDER BY (MAX(x.day) IS NULL), MAX(x.day) DESC, c.name"""
    )


def admin_answers(limit: int = 5000) -> list[dict]:
    """Every answer and every message to the circle, WITHOUT names or player ids.
    Messages appear with the question key 'quote'."""
    return _all(
        """SELECT day, circle_id, circle, question, text FROM (
               SELECT x.day AS day, x.circle_id AS circle_id, c.name AS circle,
                      a.question AS question, a.text AS text, x.id AS entry
               FROM answers a
               JOIN contributions x ON x.id = a.contribution_id
               JOIN circles c ON c.id = x.circle_id
               UNION ALL
               SELECT x.day, x.circle_id, c.name, 'quote', x.sentence, x.id
               FROM contributions x JOIN circles c ON c.id = x.circle_id
               WHERE x.sentence <> ''
           ) AS everything
           ORDER BY day DESC, entry DESC, question
           LIMIT ?""",
        limit,
    )


def join_circle(circle_id: str, player_id: str) -> None:
    _all("""INSERT INTO circle_members (circle_id, player_id) VALUES (?, ?)
            ON CONFLICT (circle_id, player_id) DO NOTHING""", circle_id, player_id)


def is_circle_member(circle_id: str, player_id: str) -> bool:
    return bool(_one("SELECT 1 AS joined FROM circle_members WHERE circle_id = ? AND player_id = ?",
                     circle_id, player_id))
