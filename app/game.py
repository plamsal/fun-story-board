"""Game rules. This file decides WHAT happens; db.py stores it and
story.py writes the story.

How a day works for one circle:

  1. A friend adds their name, answers the day's questions (a word or a short
     sentence each) and, if they like, adds a message to the circle.
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

import hashlib
import logging
import re
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import db, questions, story, styles
from .config import settings
from .filters import InputError, clean_answer, clean_circle_name, clean_name, clean_sentence

log = logging.getLogger(__name__)

ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alike characters
PLAYER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_writing: set[tuple[str, str]] = set()  # (circle, day) stories being written now
_last_failure: dict[tuple[str, str], float] = {}
_circles_made: dict[str, list[float]] = {}  # visitor -> times they created a circle


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


def allow_new_circle(visitor: str) -> bool:
    """A simple brake so one visitor cannot create circles without end."""
    hour_ago = time.monotonic() - 3600
    recent = [t for t in _circles_made.get(visitor, []) if t > hour_ago]
    if len(recent) >= settings.circles_per_hour:
        _circles_made[visitor] = recent
        return False
    _circles_made[visitor] = recent + [time.monotonic()]
    return True


def create_circle(name: str | None, people_limit: str | int | None, style: str | None = None) -> dict:
    clean = clean_circle_name(name)
    try:
        limit = int(people_limit or settings.default_people_limit)
    except ValueError:
        limit = settings.default_people_limit
    limit = max(settings.min_people_limit, min(settings.max_people_limit, limit))
    style = style if styles.is_valid(style) else "classic"

    circle_id = "".join(secrets.choice(ID_ALPHABET) for _ in range(8))
    db.insert_circle(circle_id, clean, limit, style)
    return db.get_circle(circle_id)


def get_circle(circle_id: str) -> dict | None:
    return db.get_circle((circle_id or "").lower())


# ---------- adding words ----------

def check_words(form: dict) -> tuple[dict, dict]:
    """Clean the form. Returns (clean values, {field: error message})."""
    clean, errors = {"answers": {}}, {}
    for q in questions.QUESTIONS:
        raw = (form.get(q.key) or "").strip()
        if not raw and q.optional:
            continue  # skipped, which is fine
        try:
            clean["answers"][q.key] = clean_answer(raw)
        except InputError as err:
            errors[q.key] = str(err)
    for field, check in {"name": clean_name, "sentence": clean_sentence}.items():
        try:
            clean[field] = check(form.get(field))
        except InputError as err:
            errors[field] = str(err)
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
        circle = db.get_circle(circle_id)
        style = styles.style_for_day(circle["style"], circle_id, day)
        # Loop in case another friend joins while the story is being written.
        while needs_story(circle_id, day):
            contributions = db.list_contributions(circle_id, day)
            result = await story.write_story(contributions, style)
            db.save_story(circle_id, day, result.title, result.text, result.closing,
                          len(contributions), result.source, style.key, result.matches)
        _last_failure.pop(key, None)
    except Exception:
        log.exception("Story failed for circle %s on %s", circle_id, day)
        _last_failure[key] = time.monotonic()
    finally:
        _writing.discard(key)


def days_needing_story(circle: dict) -> list[str]:
    return db.list_days_needing_story(circle["id"])


# ---------- what to show ----------

def lucky_number(day: str, person: dict) -> int:
    """A number from 1 to 99, worked out from the friend's own name and answers and
    the date. The same words on the same day always give the same number. It is
    for fun: it predicts nothing."""
    seed = "|".join([day, person["name"].lower(), *(t.lower() for t in person["answers"].values())])
    return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:4], "big") % 99 + 1


def build_story_view(saved: dict, contributions: list[dict], viewer_name: str | None = None) -> dict:
    """A saved story plus the friends in it, prepared for the page."""
    style = styles.get(saved["style"])
    people = [{**c, "lucky": lucky_number(saved["day"], c)} for c in contributions]
    kinds = questions.in_order({key: "" for c in contributions for key in c["answers"]})
    # Put the viewer's own matches first, and say "You" instead of their name.
    matches = []
    for match in saved["matches"]:
        mine = viewer_name in match["names"]
        names = ["You" if n == viewer_name else n for n in match["names"]]
        matches.append({"names": sorted(names, key=lambda n: n != "You"), "why": match["why"], "mine": mine})
    matches.sort(key=lambda m: not m["mine"])
    return {
        "day": saved["day"],
        "date": nice_date(saved["day"]),
        "title": saved["title"],
        "closing": saved["closing"],
        "paragraphs": story.to_paragraphs(saved["text"], contributions),
        "people": people,
        "legend": [{"key": key, "label": questions.label(key).lower()} for key in kinds],
        "quotes": [{"name": p["name"], "text": p["sentence"]} for p in people if p.get("sentence")],
        "my_lucky": next((p["lucky"] for p in people if p["name"] == viewer_name), None),
        "version": saved["people"],
        "source": saved["source"],
        "style": style.key,
        "kind": f"{style.article} {style.label}",  # "a fable", "an adventure"
        "matches": matches,
    }


def story_view(circle: dict, day: str, viewer_name: str | None = None) -> dict | None:
    saved = db.get_story(circle["id"], day)
    if not saved:
        return None
    # Only credit the friends this version of the story includes.
    included = db.list_contributions(circle["id"], day)[: saved["people"]]
    return build_story_view(saved, included, viewer_name)


def today_view(circle: dict, player_id: str | None, is_admin: bool = False) -> dict:
    """Everything the today page needs for this visitor."""
    day = today()
    people = db.count_people(circle["id"], day)
    limit = circle["people_limit"]
    mine = db.get_contribution(circle["id"], day, player_id) if valid_player_id(player_id) else None
    saved = db.get_story(circle["id"], day)
    version = saved["people"] if saved else 0
    full = people >= limit

    if saved and not mine:
        phase = "story"
    elif mine:
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
        "story": story_view(circle, day, mine["name"] if mine else None) if phase == "story" else None,
        "greeting": greeting(),
        "style": styles.style_for_day(circle["style"], circle["id"], day),
    }


def archive(circle: dict, player_id: str | None = None,
            month: str | None = None, style: str | None = None, is_admin: bool = False) -> dict:
    """Past stories, grouped by month, with optional month and style filters.

    Today's story is listed too, but only for a visitor who may read it
    (they added words today, or the day is closed).
    """
    day = today()
    can_read_today = today_view(circle, player_id, is_admin)["phase"] == "story"
    rows = [s for s in db.list_stories(circle["id"], up_to_day=day)
            if s["day"] < day or can_read_today]

    stories = [
        {
            "day": s["day"],
            "date": nice_date(s["day"]),
            "month": s["day"][:7],
            "title": s["title"],
            "people": s["people"],
            "style": s["style"],
            "kind": styles.get(s["style"]).label,
            "preview": story.plain_text(s["text"])[:120],
            "is_today": s["day"] == day,
            "url": f"/c/{circle['id']}" if s["day"] == day else f"/c/{circle['id']}/d/{s['day']}",
        }
        for s in rows
    ]

    # Filter choices, with how many stories each holds.
    months, kinds = {}, {}
    for s in stories:
        months[s["month"]] = months.get(s["month"], 0) + 1
        kinds[s["style"]] = kinds.get(s["style"], 0) + 1
    month = month if month in months else None
    style = style if style in kinds else None

    shown = [s for s in stories
             if (not month or s["month"] == month) and (not style or s["style"] == style)]
    groups = []  # [{"label": "November 2026", "stories": [...]}], newest month first
    for s in shown:
        label = f"{datetime.strptime(s['month'], '%Y-%m'):%B %Y}"
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "stories": []})
        groups[-1]["stories"].append(s)

    return {
        "total": len(stories),
        "shown": len(shown),
        "groups": groups,
        "months": [{"key": k, "label": f"{datetime.strptime(k, '%Y-%m'):%b %Y}", "count": n}
                   for k, n in months.items()],
        "styles": [{"key": k, "label": styles.get(k).blurb.split(":")[0], "count": n}
                   for k, n in kinds.items()],
        "month": month,
        "style": style,
    }


# ---------- your circles ----------

CIRCLE_ID_RE = re.compile(r"^[a-z0-9]{8}$")
MAX_REMEMBERED = 12


def remembered_ids(cookie: str | None, add: str | None = None) -> list[str]:
    """Circle ids kept in this browser's cookie, newest first. `add` moves one to the front."""
    ids = [i for i in (cookie or "").split(".") if CIRCLE_ID_RE.match(i)]
    if add:
        ids = [add] + [i for i in ids if i != add]
    return list(dict.fromkeys(ids))[:MAX_REMEMBERED]


def your_circles(cookie: str | None, player_id: str | None) -> list[dict]:
    """The circles this browser has opened, for the home page."""
    ids = [i for i in remembered_ids(cookie) if db.is_circle_member(i, player_id or "")]
    found = {c["id"]: c for c in db.list_circles(ids, today(), player_id or "")}
    circles = []
    for circle_id in ids:
        c = found.get(circle_id)
        if c:
            circles.append({
                "id": c["id"], "name": c["name"], "people": c["people"], "limit": c["people_limit"],
                "joined": bool(c["mine"]), "full": c["people"] >= c["people_limit"],
            })
    return circles


def past_story(circle: dict, day: str) -> dict | None:
    """A finished day's story. Today's story is only shown on the today page."""
    if not DAY_RE.match(day or "") or day >= today():
        return None
    return story_view(circle, day)


def card_text(circle: dict, day: str | None = None) -> dict | None:
    """Title and closing line for the share card (no names, no words)."""
    if day and not DAY_RE.match(day):
        return None
    saved = db.get_story(circle["id"], day) if day else db.get_latest_story(circle["id"])
    if not saved or not saved["closing"]:
        return None
    return {"title": saved["title"], "closing": saved["closing"], "date": nice_date(saved["day"])}
