"""Game rules. This file decides WHAT happens; db.py stores it and
story.py writes the story.

How a day works for one circle:

  1. A friend adds their name and three words.
  2. The story is rewritten to include them, and they can read it right away.
     So the first friend of the morning already gets a story, and it grows
     richer with each friend who joins.
  3. Friends who have not added words yet cannot see today's story.
  4. When the circle's limit is reached the day is closed and the story is final.
     At midnight a new day starts either way.

What a visitor sees (the "phase"):

  form     they have not added words today, and there is still room
  writing  the story that includes them is being written
  story    the story is ready to read
"""

import logging
import re
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import db, story
from .config import settings
from .filters import InputError, clean_circle_name, clean_name, clean_word
from .questions import KEYS

log = logging.getLogger(__name__)

ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alike characters
PLAYER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_writing: set[tuple[str, str]] = set()  # (circle, day) stories being written now
_last_failure: dict[tuple[str, str], float] = {}


# ---------- time ----------

def now() -> datetime:
    return datetime.now(ZoneInfo(settings.time_zone))


def today() -> str:
    return now().strftime("%Y-%m-%d")


def greeting() -> str:
    hour = now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def nice_date(day: str) -> str:
    date = datetime.strptime(day, "%Y-%m-%d")
    return f"{date:%A}, {date:%B} {date.day}"


# ---------- circles and players ----------

def new_player_id() -> str:
    return secrets.token_urlsafe(18)


def valid_player_id(player_id: str | None) -> bool:
    return bool(player_id and PLAYER_ID_RE.match(player_id))


def create_circle(name: str | None, people_limit: str | int | None) -> dict:
    clean = clean_circle_name(name)
    try:
        limit = int(people_limit or settings.default_people_limit)
    except ValueError:
        limit = settings.default_people_limit
    limit = max(settings.min_people_limit, min(settings.max_people_limit, limit))

    circle_id = "".join(secrets.choice(ID_ALPHABET) for _ in range(8))
    db.insert_circle(circle_id, clean, limit)
    return db.get_circle(circle_id)


def get_circle(circle_id: str) -> dict | None:
    return db.get_circle((circle_id or "").lower())


# ---------- adding words ----------

def check_words(form: dict) -> tuple[dict, dict]:
    """Clean the form. Returns (clean values, {field: error message})."""
    clean, errors = {}, {}
    for key in KEYS:
        try:
            clean[key] = clean_word(form.get(key))
        except InputError as err:
            errors[key] = str(err)
    try:
        clean["name"] = clean_name(form.get("name"))
    except InputError as err:
        errors["name"] = str(err)
    return clean, errors


def add_words(circle: dict, player_id: str, form: dict) -> dict:
    """Save a friend's words. Returns {field: error}; empty means saved."""
    clean, errors = check_words(form)
    if errors:
        return errors

    day = today()
    if db.get_contribution(circle["id"], day, player_id):
        return {}  # already in today; just show them the story
    if db.count_people(circle["id"], day) >= circle["people_limit"]:
        return {"form": "Today's story is full. Come back tomorrow!"}

    db.insert_contribution(circle["id"], day, player_id, **clean)
    return {}


# ---------- writing the story ----------

def needs_story(circle_id: str, day: str) -> bool:
    """True when friends have added words the saved story does not include."""
    saved = db.get_story(circle_id, day)
    return db.count_people(circle_id, day) > (saved["people"] if saved else 0)


async def write_story_job(circle_id: str, day: str) -> None:
    """Bring the story up to date. Safe to call often; only one runs at a time."""
    key = (circle_id, day)
    if key in _writing:
        return
    if time.monotonic() - _last_failure.get(key, -1e9) < settings.retry_after_seconds:
        return

    _writing.add(key)
    try:
        # Loop in case another friend joins while the story is being written.
        while needs_story(circle_id, day):
            contributions = db.list_contributions(circle_id, day)
            result = await story.write_story(contributions)
            db.save_story(circle_id, day, result.title, result.text, result.closing,
                          len(contributions), result.source)
        _last_failure.pop(key, None)
    except Exception:
        log.exception("Story failed for circle %s on %s", circle_id, day)
        _last_failure[key] = time.monotonic()
    finally:
        _writing.discard(key)


def days_needing_story(circle: dict) -> list[str]:
    return db.list_days_needing_story(circle["id"])


# ---------- what to show ----------

def story_view(circle: dict, day: str) -> dict | None:
    """The saved story for a day, prepared for the page."""
    saved = db.get_story(circle["id"], day)
    if not saved:
        return None
    contributions = db.list_contributions(circle["id"], day)
    # Only credit the friends this version of the story includes.
    included = contributions[: saved["people"]]
    return {
        "day": day,
        "date": nice_date(day),
        "title": saved["title"],
        "closing": saved["closing"],
        "paragraphs": story.to_paragraphs(saved["text"], included),
        "people": included,
        "version": saved["people"],
        "source": saved["source"],
    }


def today_view(circle: dict, player_id: str | None) -> dict:
    """Everything the today page needs for this visitor."""
    day = today()
    people = db.count_people(circle["id"], day)
    limit = circle["people_limit"]
    mine = db.get_contribution(circle["id"], day, player_id) if valid_player_id(player_id) else None
    saved = db.get_story(circle["id"], day)
    version = saved["people"] if saved else 0
    full = people >= limit

    if mine:
        # Ready once the story includes this friend.
        phase = "story" if version >= mine["position"] else "writing"
    elif full:
        # Day is closed: everyone may read the final story.
        phase = "story" if version >= limit else "writing"
    else:
        phase = "form"

    return {
        "day": day,
        "date": nice_date(day),
        "phase": phase,
        "people": people,
        "limit": limit,
        "full": full,
        "mine": mine,
        "version": version,
        "story": story_view(circle, day) if phase == "story" else None,
        "greeting": greeting(),
    }


def archive(circle: dict) -> list[dict]:
    return [
        {
            "day": s["day"],
            "date": nice_date(s["day"]),
            "title": s["title"],
            "people": s["people"],
            "preview": story.plain_text(s["text"])[:120],
        }
        for s in db.list_stories(circle["id"], before_day=today())
    ]


def past_story(circle: dict, day: str) -> dict | None:
    """A finished day's story. Today's story is only shown on the today page."""
    if not DAY_RE.match(day or "") or day >= today():
        return None
    return story_view(circle, day)
