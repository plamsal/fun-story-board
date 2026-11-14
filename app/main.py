"""Web server: pages are drawn in Python (Jinja2 templates in app/templates).

    GET  /                   home: sample story + create a circle
    POST /circles            create it, then go to the circle page
    GET  /c/{id}             today: add words -> wait -> read the story
    POST /c/{id}/words       add your name, three answers and optional message
    GET  /c/{id}/status      tiny JSON the page polls while the story is written
    GET  /c/{id}/card.png    shareable picture (title + closing line)
    GET  /c/{id}/archive     all stories, by month (?month=2026-11&style=fable to filter)
    GET  /c/{id}/d/{day}     one past story
    GET  /privacy            who can read what, in plain words
    GET  /admin              for the person who runs the app (needs ADMIN_KEY)
    GET  /healthz            "ok" (used by the host to check the app is up)

Run with:  uvicorn app.main:app --reload
"""

import hmac
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import admin, db, game, styles
from .card import make_card
from .config import settings
from .filters import InputError
from .questions import QUESTIONS, QUOTE_ASK, QUOTE_HINT
from .sample import sample_story

HERE = Path(__file__).parent
PLAYER_COOKIE = "sb_player"
CIRCLES_COOKIE = "sb_circles"  # the circles this browser has opened
ONE_YEAR = 60 * 60 * 24 * 365

app = FastAPI(title="Story Board", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def and_join(names) -> str:
    """["Asha", "Ben", "Cai"] -> "Asha, Ben and Cai"."""
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


templates.env.filters["and_join"] = and_join


# ---------- helpers ----------

def page(request: Request, name: str, status: int = 200, **context) -> HTMLResponse:
    """Draw a template and make sure this browser has a player id cookie."""
    response = templates.TemplateResponse(request, name, context, status_code=status)
    if not game.valid_player_id(request.cookies.get(PLAYER_COOKIE)):
        _set_player_cookie(request, response)
    return response


def _set_player_cookie(request: Request, response) -> None:
    response.set_cookie(PLAYER_COOKIE, request.state.player_id, max_age=ONE_YEAR,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")


def remember_circle(request: Request, response, circle: dict):
    """Keep this circle in the browser's "Your circles" list."""
    ids = game.remembered_ids(request.cookies.get(CIRCLES_COOKIE), add=circle["id"])
    response.set_cookie(CIRCLES_COOKIE, ".".join(ids), max_age=ONE_YEAR,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")
    return response


@app.middleware("http")
async def give_player_id(request: Request, call_next):
    """Each browser gets a random id, so a person adds words once per day."""
    cookie = request.cookies.get(PLAYER_COOKIE)
    request.state.player_id = cookie if game.valid_player_id(cookie) else game.new_player_id()
    request.state.is_admin = admin.is_signed_in(request.cookies.get(admin.COOKIE))
    if request.url.path.startswith("/c/"):
        circle_id = request.url.path.split("/")[2]
        circle = game.get_circle(circle_id)
        invite = request.query_params.get("invite", "")
        invited = bool(circle and invite and hmac.compare_digest(invite.encode(), circle["invite_token"].encode()))
        if not circle or not (request.state.is_admin or invited or
                              db.is_circle_member(circle_id, request.state.player_id)):
            return not_found(request)
        if invited:
            db.join_circle(circle_id, request.state.player_id)
    response = await call_next(request)
    if not game.valid_player_id(cookie):
        _set_player_cookie(request, response)
    if request.url.path.startswith(("/c/", "/admin")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


def not_found(request: Request) -> HTMLResponse:
    return page(request, "problem.html", status=404, title="Nothing here.",
                message="This page does not exist. The link may be mistyped.")


def catch_up(circle: dict, background: BackgroundTasks) -> None:
    """Write any story that is behind (today's, or a day that failed earlier)."""
    for day in game.days_needing_story(circle):
        background.add_task(game.write_story_job, circle["id"], day)


def circle_urls(request: Request, circle: dict) -> dict:
    """Full links for sharing and for the link-preview picture."""
    share_url = str(request.url_for("today", circle_id=circle["id"]))
    return {"share_url": f"{share_url}?invite={circle['invite_token']}",
            "card_url": f"{share_url}/card.png"}


# ---------- home ----------

def _home(request: Request, status: int = 200, form: dict | None = None, error: str = ""):
    limits = [n for n in (3, 4, 5, 6, 8, 10, 12)
              if settings.min_people_limit <= n <= settings.max_people_limit]
    return page(request, "home.html", status=status, limits=limits, style_choices=styles.CHOICES,
                form=form or {}, error=error, story=sample_story(), view=None,
                your_circles=game.your_circles(request.cookies.get(CIRCLES_COOKIE),
                                               request.state.player_id),
                card_url=str(request.url_for("default_card")))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return _home(request)


@app.post("/circles")
async def create_circle(request: Request):
    form = dict(await request.form())
    visitor = request.client.host if request.client else "unknown"
    if not game.allow_new_circle(visitor):
        return _home(request, 429, form, "That is a lot of circles. Please try again in an hour.")
    try:
        circle = game.create_circle(form.get("name"), form.get("people_limit"), form.get("style"))
    except InputError as err:
        return _home(request, 400, form, str(err))
    db.join_circle(circle["id"], request.state.player_id)
    response = RedirectResponse(f"/c/{circle['id']}?new=1", status_code=303)
    return remember_circle(request, response, circle)


@app.get("/card.png")
async def default_card():
    return Response(make_card(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return page(request, "privacy.html", contact_email=settings.contact_email)


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


# ---------- today ----------

@app.get("/c/{circle_id}", response_class=HTMLResponse)
async def today(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return not_found(request)
    if circle["archived"]:
        return RedirectResponse(f"/c/{circle_id}/archive", status_code=303)
    catch_up(circle, background)
    view = game.today_view(circle, request.state.player_id, request.state.is_admin)
    return _today_page(request, circle, view)


@app.post("/c/{circle_id}/words")
async def add_words(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return not_found(request)

    if circle["archived"]:
        return page(request, "problem.html", status=409, title="This circle is archived",
                    message="Its past stories are still available. New answers are paused.")
    form = dict(await request.form())
    errors = game.add_words(circle, request.state.player_id, form)
    if errors:
        view = game.today_view(circle, request.state.player_id, request.state.is_admin)
        return _today_page(request, circle, view, status=400, form=form, errors=errors)

    background.add_task(game.write_story_job, circle["id"], game.today())
    response = RedirectResponse(f"/c/{circle['id']}", status_code=303)
    _set_player_cookie(request, response)  # this may be the browser's very first request
    return response


def _today_page(request, circle, view, status=200, form=None, errors=None) -> HTMLResponse:
    template = {"form": "words.html", "writing": "writing.html", "story": "story.html"}[view["phase"]]
    return remember_circle(request, page(
        request, template, status=status,
        circle=circle, view=view, story=view["story"],
        questions=QUESTIONS, quote_ask=QUOTE_ASK, quote_hint=QUOTE_HINT,
        form=form or {}, errors=errors or {},
        is_new=request.query_params.get("new") == "1",
        is_today=True, **circle_urls(request, circle),
    ), circle)


@app.get("/c/{circle_id}/status")
async def status(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return JSONResponse({"error": "not found"}, status_code=404)
    catch_up(circle, background)
    view = game.today_view(circle, request.state.player_id, request.state.is_admin)
    return {"phase": view["phase"], "version": view["version"], "people": view["people"]}


@app.get("/c/{circle_id}/card.png")
async def card(circle_id: str, day: str | None = None):
    """The share picture for one day, or for the circle's newest story."""
    circle = game.get_circle(circle_id)
    if not circle:
        return Response(status_code=404)
    text = game.card_text(circle, day) or {"closing": "", "title": ""}
    return Response(make_card(text["closing"], text["title"]), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=300"})


# ---------- past stories ----------

@app.get("/c/{circle_id}/archive", response_class=HTMLResponse)
async def archive(request: Request, circle_id: str, background: BackgroundTasks,
                  month: str | None = None, style: str | None = None):
    circle = game.get_circle(circle_id)
    if not circle:
        return not_found(request)
    catch_up(circle, background)
    listing = game.archive(circle, request.state.player_id, month, style, request.state.is_admin)
    return page(request, "archive.html", circle=circle, archive=listing,
                **circle_urls(request, circle))


@app.get("/c/{circle_id}/d/{day}", response_class=HTMLResponse)
async def past_story(request: Request, circle_id: str, day: str):
    circle = game.get_circle(circle_id)
    if not circle:
        return not_found(request)
    if day == game.today():
        return RedirectResponse(f"/c/{circle['id']}", status_code=303)
    story = game.past_story(circle, day)
    if not story:
        return not_found(request)
    return page(request, "story.html", circle=circle, story=story, view=None,
                is_today=False, is_new=False, **circle_urls(request, circle))


# ---------- admin (only when ADMIN_KEY is set; see admin.py) ----------

def _visitor(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, question: str | None = None, circle: str | None = None):
    if not admin.enabled():
        return page(request, "problem.html", status=503, title="Admin setup needed",
                    message="Set ADMIN_KEY in Render to a secret of at least 12 characters, then redeploy.")
    if not admin.is_signed_in(request.cookies.get(admin.COOKIE)):
        return page(request, "admin_login.html", error="")
    return page(request, "admin.html", data=admin.overview(question, circle),
                csrf_token=admin.csrf_token(request.cookies[admin.COOKIE]))


@app.post("/admin")
async def admin_sign_in(request: Request):
    if not admin.enabled():
        return not_found(request)
    form = dict(await request.form())
    token = admin.sign_in(str(form.get("key", "")), _visitor(request))
    if not token:
        return page(request, "admin_login.html", status=403, error="That key did not work.")
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(admin.COOKIE, token, max_age=60 * 60 * 12, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https")
    return response


@app.get("/admin/answers.csv")
async def admin_download(request: Request):
    if not admin.is_signed_in(request.cookies.get(admin.COOKIE)):
        return Response(status_code=404)
    return Response(admin.answers_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="story-board-answers.csv"'})


@app.post("/admin/logout")
async def admin_logout():
    response = RedirectResponse("/admin", status_code=303)
    response.delete_cookie(admin.COOKIE)
    return response


@app.post("/admin/circles/{circle_id}/archive")
async def admin_archive_circle(request: Request, circle_id: str):
    if not admin.is_signed_in(request.cookies.get(admin.COOKIE)):
        return RedirectResponse("/admin", status_code=303)
    form = await request.form()
    submitted = str(form.get("csrf_token", ""))
    expected = admin.csrf_token(request.cookies[admin.COOKIE])
    if not hmac.compare_digest(submitted.encode(), expected.encode()):
        return page(request, "problem.html", status=403, title="Please refresh Admin",
                    message="Open /admin again and retry the archive action from the refreshed page.")
    if not game.get_circle(circle_id):
        return not_found(request)
    db.set_circle_archived(circle_id, form.get("archived") == "1")
    return RedirectResponse("/admin", status_code=303)
