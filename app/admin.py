"""The admin page: only for the person who runs the app.

    /admin               all circles, and every answer WITHOUT names
    /admin/answers.csv   the same answers as a spreadsheet file

It is switched on by setting ADMIN_KEY (a long secret you choose) in the
host's settings. Without it, the admin pages do not exist.

Names and player ids are never shown here or in the download. Opening a
circle from the list shows that circle's stories as its members see them.
"""

import csv
import hashlib
import hmac
import io
import time

from . import db, questions, styles
from .config import settings

COOKIE = "sb_admin"
MAX_TRIES_PER_HOUR = 8
_tries: dict[str, list[float]] = {}  # visitor -> times of wrong keys


def enabled() -> bool:
    return len(settings.admin_key) >= 12


def _token() -> str:
    """What the browser keeps after signing in. It is derived from the key, not the key itself."""
    return hmac.new(settings.admin_key.encode(), b"story-board-admin", hashlib.sha256).hexdigest()


def is_signed_in(cookie: str | None) -> bool:
    return enabled() and bool(cookie) and hmac.compare_digest(cookie, _token())


def sign_in(key: str, visitor: str) -> str | None:
    """Returns the cookie value if the key is right, otherwise None."""
    hour_ago = time.monotonic() - 3600
    recent = [t for t in _tries.get(visitor, []) if t > hour_ago]
    if not enabled() or len(recent) >= MAX_TRIES_PER_HOUR:
        return None
    if hmac.compare_digest(key.encode(), settings.admin_key.encode()):
        return _token()
    _tries[visitor] = recent + [time.monotonic()]
    return None


def question_label(key: str) -> str:
    return "Quote" if key == "quote" else questions.label(key)


def overview(question: str | None = None, circle_id: str | None = None) -> dict:
    """Everything the admin page shows. Answers carry no names."""
    answers = db.admin_answers()
    counts: dict[str, int] = {}
    for a in answers:
        counts[a["question"]] = counts.get(a["question"], 0) + 1
    order = list(questions.ALL) + ["quote"]
    filters = [{"key": k, "label": question_label(k), "count": counts[k]}
               for k in sorted(counts, key=lambda k: order.index(k) if k in order else 99)]

    question = question if question in counts else None
    shown = [a for a in answers
             if (not question or a["question"] == question)
             and (not circle_id or a["circle_id"] == circle_id)]
    circles = db.admin_circles()
    return {
        "totals": db.admin_totals(),
        "circles": [{**c, "style_label": styles.SURPRISE_BLURB.split(":")[0] if c["style"] == styles.SURPRISE
                     else styles.get(c["style"]).blurb.split(":")[0]} for c in circles],
        "filters": filters,
        "question": question,
        "circle": next((c for c in circles if c["id"] == circle_id), None),
        "answers": [{**a, "label": question_label(a["question"])} for a in shown[:500]],
        "shown": len(shown),
    }


def answers_csv() -> str:
    """All answers as CSV text: day, circle, question, answer. No names."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["day", "circle_id", "circle", "question", "answer"])
    for a in db.admin_answers(limit=100000):
        text = a["text"]
        if text[:1] in "=+-@":  # stop spreadsheets from treating an answer as a formula
            text = "'" + text
        writer.writerow([a["day"], a["circle_id"], a["circle"], a["question"], text])
    return out.getvalue()


def csrf_token(cookie: str) -> str:
    """Bind form submissions to the authenticated admin session."""
    return hmac.new(settings.admin_key.encode(),
                    ("archive-form:" + cookie).encode(), hashlib.sha256).hexdigest()
