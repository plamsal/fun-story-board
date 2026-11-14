"""Web server: pages are drawn in Python (Jinja2 templates in app/templates).

    GET  /                   home: create a circle
    POST /circles            create it, then go to the circle page
    GET  /c/{id}             today: add words -> wait -> read the story
    POST /c/{id}/words       add your name and three words
    GET  /c/{id}/status      tiny JSON the page polls while the story is written
    GET  /c/{id}/archive     past stories
    GET  /c/{id}/d/{day}     one past story

Run with:  uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import game
from .config import settings
from .filters import InputError
from .questions import QUESTIONS

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
        response.set_cookie(PLAYER_COOKIE, request.state.player_id, max_age=ONE_YEAR,
                            httponly=True, samesite="lax")
    return response


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


# ---------- home ----------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return page(request, "home.html", limits=_limit_choices(), form={}, error="")


@app.post("/circles")
async def create_circle(request: Request):
    form = dict(await request.form())
    try:
        circle = game.create_circle(form.get("name"), form.get("people_limit"))
    except InputError as err:
        return page(request, "home.html", status=400, limits=_limit_choices(),
                    form=form, error=str(err))
    return RedirectResponse(f"/c/{circle['id']}?new=1", status_code=303)


def _limit_choices() -> list[int]:
    return [n for n in (3, 4, 5, 6, 8, 10, 12)
            if settings.min_people_limit <= n <= settings.max_people_limit]


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
    # Set the cookie here too: this may be the browser's very first request.
    response.set_cookie(PLAYER_COOKIE, request.state.player_id, max_age=ONE_YEAR,
                        httponly=True, samesite="lax")
    return response


def _today_page(request, circle, view, status=200, form=None, errors=None) -> HTMLResponse:
    template = {"form": "words.html", "writing": "writing.html", "story": "story.html"}[view["phase"]]
    return page(
        request, template, status=status,
        circle=circle, view=view, story=view["story"], questions=QUESTIONS,
        form=form or {}, errors=errors or {},
        is_new=request.query_params.get("new") == "1",
        share_url=str(request.url_for("today", circle_id=circle["id"])),
        is_today=True,
    )


@app.get("/c/{circle_id}/status")
async def status(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return JSONResponse({"error": "not found"}, status_code=404)
    catch_up(circle, background)
    view = game.today_view(circle, request.state.player_id)
    return {"phase": view["phase"], "version": view["version"], "people": view["people"]}


# ---------- past stories ----------

@app.get("/c/{circle_id}/archive", response_class=HTMLResponse)
async def archive(request: Request, circle_id: str, background: BackgroundTasks):
    circle = game.get_circle(circle_id)
    if not circle:
        return not_found(request)
    catch_up(circle, background)
    return page(request, "archive.html", circle=circle, stories=game.archive(circle))


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
                share_url=str(request.url_for("today", circle_id=circle["id"])),
                is_today=False, is_new=False)
