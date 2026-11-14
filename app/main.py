"""Web server: pages are drawn in Python (Jinja2 templates in app/templates).

    GET  /                   home: sample story + create a circle
    POST /circles            create it, then go to the circle page
    GET  /c/{id}             today: add words -> wait -> read the story
    POST /c/{id}/words       add your name, three words and optional sentence
    GET  /c/{id}/status      tiny JSON the page polls while the story is written
    GET  /c/{id}/card.png    shareable picture (title + closing line)
    GET  /c/{id}/archive     past stories
    GET  /c/{id}/d/{day}     one past story
    GET  /healthz            "ok" (used by the host to check the app is up)

Run with:  uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import game, styles
from .card import make_card
from .config import settings
from .filters import InputError
from .questions import QUESTIONS, SENTENCE_ASK
from .sample import sample_story

HERE = Path(__file__).parent
PLAYER_COOKIE = "sb_player"
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


@app.middleware("http")
async def give_player_id(request: Request, call_next):
    """Each browser gets a random id, so a person adds words once per day."""
    cookie = request.cookies.get(PLAYER_COOKIE)
    request.state.player_id = cookie if game.valid_player_id(cookie) else game.new_player_id()
    return await call_next(request)


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
    return {"share_url": share_url, "card_url": f"{share_url}/card.png"}


# ---------- home ----------

def _home(request: Request, status: int = 200, form: dict | None = None, error: str = ""):
    limits = [n for n in (3, 4, 5, 6, 8, 10, 12)
              if settings.min_people_limit <= n <= settings.max_people_limit]
    return page(request, "home.html", status=status, limits=limits, style_choices=styles.CHOICES,
                form=form or {}, error=error, story=sample_story(), view=None,
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
    return RedirectResponse(f"/c/{circle['id']}?new=1", status_code=303)


@app.get("/card.png")
async def default_card():
    return Response(make_card(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


# ---------- today ----------

@app.get("/c/{circle_id}", response_class=HTMLResponse)
async def today(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return not_found(request)
    catch_up(circle, background)
    view = game.today_view(circle, request.state.player_id)
    return _today_page(request, circle, view)


@app.post("/c/{circle_id}/words")
async def add_words(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return not_found(request)

    form = dict(await request.form())
    errors = game.add_words(circle, request.state.player_id, form)
    if errors:
        view = game.today_view(circle, request.state.player_id)
        return _today_page(request, circle, view, status=400, form=form, errors=errors)

    background.add_task(game.write_story_job, circle["id"], game.today())
    response = RedirectResponse(f"/c/{circle['id']}", status_code=303)
    _set_player_cookie(request, response)  # this may be the browser's very first request
    return response


def _today_page(request, circle, view, status=200, form=None, errors=None) -> HTMLResponse:
    template = {"form": "words.html", "writing": "writing.html", "story": "story.html"}[view["phase"]]
    return page(
        request, template, status=status,
        circle=circle, view=view, story=view["story"],
        questions=QUESTIONS, sentence_ask=SENTENCE_ASK,
        form=form or {}, errors=errors or {},
        is_new=request.query_params.get("new") == "1",
        is_today=True, **circle_urls(request, circle),
    )


@app.get("/c/{circle_id}/status")
async def status(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return JSONResponse({"error": "not found"}, status_code=404)
    catch_up(circle, background)
    view = game.today_view(circle, request.state.player_id)
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
async def archive(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return not_found(request)
    catch_up(circle, background)
    return page(request, "archive.html", circle=circle, stories=game.archive(circle),
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
