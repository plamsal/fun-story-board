"""Plays the game through the real web app.   Run with:  pytest"""

import asyncio
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import admin, db, game, story, styles
from app.filters import InputError, clean_answer, clean_name, clean_word
from app.main import app

# What three friends type into the form.
FRIENDS = [
    {"name": "Asha", "hope": "travel", "weight": "doubt", "strength": "mom"},
    {"name": "Ben", "hope": "rain", "weight": "money", "strength": "walks"},
    {"name": "Cai", "hope": "music", "weight": "", "strength": "naps"},  # skipped the weight question
]
ALL_ANSWERS = ["travel", "doubt", "mom", "rain", "money", "walks", "music", "naps"]


def entry(friend: dict) -> dict:
    """The same friend in the shape the database and story code use."""
    answers = {k: v for k, v in friend.items() if k not in ("name", "sentence") and v}
    return {"name": friend["name"], "sentence": friend.get("sentence", ""), "answers": answers}


def new_circle(limit=3, name="Test friends", style="classic") -> str:
    browser = TestClient(app, follow_redirects=False)
    res = browser.post("/circles", data={"name": name, "people_limit": str(limit), "style": style})
    assert res.status_code == 303
    return res.headers["location"].split("/c/")[1].split("?")[0]


def use_fake_claude(monkeypatch, reply):
    """Pretend an API key is set and make Claude answer with `reply` (text or function)."""
    asked = []

    async def fake_ask(messages):
        asked.append(messages)
        return reply(len(asked)) if callable(reply) else reply

    monkeypatch.setattr(story, "settings", dataclasses.replace(story.settings, anthropic_api_key="test"))
    monkeypatch.setattr(story, "_ask_claude", fake_ask)
    return asked


# ---------- a day in a circle ----------

def test_a_full_day():
    circle = new_circle(limit=3)
    asha, ben, cai, late = (TestClient(app) for _ in range(4))

    # A new visitor sees the questions and the disclosure, not a story.
    page = asha.get(f"/c/{circle}").text
    assert "What are you hoping for right now?" in page and "What has been weighing on you lately?" in page
    assert "Who or what is getting you through?" in page
    assert "without names" in page and 'href="/privacy"' in page

    # Foul language is stopped, the message sits on that field, other answers are kept.
    res = asha.post(f"/c/{circle}/words", data={**FRIENDS[0], "strength": "shit"})
    assert res.status_code == 400 and "keep it kind" in res.text and 'value="travel"' in res.text

    # An answer that is too long, or has odd characters, is stopped.
    res = asha.post(f"/c/{circle}/words", data={**FRIENDS[0], "hope": "a very long trip " * 6})
    assert res.status_code == 400 and "Keep it short" in res.text
    res = asha.post(f"/c/{circle}/words", data={**FRIENDS[0], "hope": "a trip [[1|x]] {{y}}"})
    assert res.status_code == 400 and "simple punctuation" in res.text

    # The hope and strength questions must be answered; the weight question may be skipped.
    res = asha.post(f"/c/{circle}/words", data={**FRIENDS[0], "hope": ""})
    assert res.status_code == 400 and "Please add a word" in res.text

    # Asha answers and can read a story with her in it straight away.
    page = asha.post(f"/c/{circle}/words", data=FRIENDS[0]).text
    assert "Good " in page and ">travel</mark>" in page and ">doubt</mark>" in page
    assert "1 of 3 friends so far" in page

    # Ben has not answered yet, so he cannot see Asha's answers.
    page = ben.get(f"/c/{circle}").text
    assert "travel" not in page and "1 friend is in" in page
    assert "travel" not in ben.get(f"/c/{circle}/d/{game.today()}").text

    # Ben joins: the story now holds both of them.
    page = ben.post(f"/c/{circle}/words", data=FRIENDS[1]).text
    assert ">rain</mark>" in page and ">travel</mark>" in page and "A story for Asha and Ben" in page
    assert asha.get(f"/c/{circle}/status").json() == {"phase": "story", "version": 2, "people": 2}

    # Answering twice does nothing.
    ben.post(f"/c/{circle}/words", data={**FRIENDS[1], "hope": "snow"})
    assert db.count_people(circle, game.today()) == 2

    # Cai skips the weight question and fills the circle: the day is closed.
    page = cai.post(f"/c/{circle}/words", data=FRIENDS[2]).text
    assert "All 3 friends are in" in page
    for answer in ALL_ANSWERS:
        assert f">{answer}</mark>" in page
    for friend in FRIENDS:
        assert f">{friend['name']}</mark>" in page
    assert db.list_contributions(circle, game.today())[2]["answers"] == {"hope": "music", "strength": "naps"}

    # A late visitor can read the finished story but cannot answer.
    page = late.get(f"/c/{circle}").text
    assert "All 3 friends are in" in page and "<form" not in page
    late.post(f"/c/{circle}/words", data={"name": "Dee", "hope": "sun", "strength": "dog"})
    assert db.count_people(circle, game.today()) == 3


def test_past_days_get_their_story_and_show_in_the_list():
    circle = new_circle(limit=8, name="Old days")
    for n, friend in enumerate(FRIENDS):
        db.insert_contribution(circle, "2020-01-01", f"player-{n}", **entry(friend))

    browser = TestClient(app)
    browser.get(f"/c/{circle}")  # opening the circle writes any story that is behind
    listing = browser.get(f"/c/{circle}/archive").text
    assert "Wednesday, January 1" in listing and "3 friends" in listing and "January 2020" in listing
    page = browser.get(f"/c/{circle}/d/2020-01-01")
    assert page.status_code == 200 and ">mom</mark>" in page.text


def test_unknown_pages_are_404():
    browser = TestClient(app)
    assert browser.get("/c/nope1234").status_code == 404
    circle = new_circle()
    assert browser.get(f"/c/{circle}/d/2019-05-05").status_code == 404
    assert browser.get(f"/c/{circle}/d/not-a-day").status_code == 404


def test_health_check_and_privacy_page():
    browser = TestClient(app)
    assert browser.get("/healthz").text == "ok"
    privacy = browser.get("/privacy").text
    assert "Who can read what" in privacy and "without names" in privacy and "Claude" in privacy


# ---------- input rules ----------

def test_word_name_and_answer_rules():
    assert clean_word("  Passion ") == "passion"
    assert clean_word("well-being") == "well-being"
    assert clean_word("niño") == "niño"
    assert clean_word("god") == "god"  # allowed on purpose
    assert clean_name("  mary   ann ") == "mary ann"
    for bad in ["", "two words", "abc123", "x" * 21, "peace!", "fuck"]:
        with pytest.raises(InputError):
            clean_word(bad)
    with pytest.raises(InputError):
        clean_name("<script>")

    # An answer can be one word or a short sentence.
    assert clean_answer(" Rain ") == "rain"
    assert clean_answer("  my grandmother's   cooking. ") == "my grandmother's cooking"
    for bad in ["", "abc123", "x" * 21, "word " * 20, "a [bracket] here", "you are a shit friend"]:
        with pytest.raises(InputError):
            clean_answer(bad)


def test_circle_creation_is_limited_per_visitor(monkeypatch):
    monkeypatch.setattr(game, "settings", dataclasses.replace(game.settings, circles_per_hour=2))
    monkeypatch.setattr(game, "_circles_made", {})
    browser = TestClient(app, follow_redirects=False)
    codes = [browser.post("/circles", data={"name": "Many", "people_limit": "3"}).status_code for _ in range(3)]
    assert codes == [303, 303, 429]


# ---------- the story engine ----------

def test_story_marks_and_credits():
    people = [{"name": "Asha", "sentence": "", "answers": {"hope": "rain", "weight": "tea", "strength": "my grandmother's cooking"}},
              {"name": "Ben", "sentence": "", "answers": {"hope": "the sea at night", "weight": "tea", "strength": "hug"}}]
    answers = story.number_answers(people)
    # Each distinct answer gets a number; the shared "tea" has one number and two givers.
    assert [(a["id"], a["text"], a["single"]) for a in answers] == [
        (1, "rain", True), (2, "tea", True), (3, "my grandmother's cooking", False),
        (4, "the sea at night", False), (5, "hug", True)]
    assert answers[1]["givers"] == [("weight", "Asha"), ("weight", "Ben")]

    # Small marking slips are repaired: a missing number, an unmarked word, an unmarked name.
    text = "{{Asha}} wanted [[rain]]. Ben poured tea and gave a Hug by [[4|the dark water]]."
    fixed = story.tidy_marks(text, answers, ["Asha", "Ben"])
    assert fixed == "{{Asha}} wanted [[1|rain]]. {{Ben}} poured [[2|tea]] and gave a [[5|Hug]] by [[4|the dark water]]."
    # A sentence answer that was never woven in cannot be repaired, so it is reported.
    assert story.missing_items(fixed, answers, ["Asha", "Ben"]) == ['answer 3 ("my grandmother\'s cooking")']
    # A word inside an already marked phrase is left alone.
    assert story.tidy_marks("[[4|rain on the sea]]", answers, []) == "[[4|rain on the sea]]"

    pieces = story.to_paragraphs("{{Asha}} poured [[2|tea]] near [[3|her grandmother's kitchen]].\n\nThe end.", people)
    assert len(pieces) == 2
    assert pieces[0][0] == {"type": "name", "text": "Asha",
                            "credit": "Asha gave: rain · tea · my grandmother's cooking"}
    assert pieces[0][2]["credit"] == "“tea” was Asha's weight word and Ben's weight word."
    assert pieces[0][4] == {"type": "word", "text": "her grandmother's kitchen", "kind": "strength",
                            "credit": "From Asha's strength: “my grandmother's cooking”"}
    # Stories saved before answers had numbers still display.
    old = story.to_paragraphs("{{Ben}} gave a [[hug]].", people)
    assert old[0][2]["text"] == "hug" and old[0][2]["kind"] == "strength"
    assert story.strip_marks("{{Ben}} saw [[4|the dark water]] and [[rain]].") == "Ben saw the dark water and rain."


def test_claude_is_asked_again_when_someone_is_left_out(monkeypatch):
    first = ("TITLE: The Long Way Home\n\n{{Asha}} set [[2|doubt]] down, thought of [[3|mom]] and chose [[1|travel]].\n\n"
             "TODAY: Take one bold step.")
    second = first.replace("\n\nTODAY", "\n\n{{Ben}} forgot about [[5|money]] on one of those [[6|walks]] in the [[4|rain]].\n\nTODAY")
    asked = use_fake_claude(monkeypatch, lambda n: first if n == 1 else second)

    result = asyncio.run(story.write_story([entry(f) for f in FRIENDS[:2]], styles.get("fable")))
    assert len(asked) == 2
    assert "the name Ben" in asked[1][-1]["content"] and 'answer 4 ("rain")' in asked[1][-1]["content"]
    assert result.title == "The Long Way Home" and result.closing == "Take one bold step."
    assert result.source == "claude" and "{{Ben}}" in result.text
    assert "TITLE" not in result.text and "TODAY" not in result.text

    # The request names every friend with their numbered answers, the questions, and the style.
    request = asked[0][0]["content"]
    assert '- Asha: hope (1) = "travel"; weight (2) = "doubt"; strength (3) = "mom"' in request
    assert '- Weight ("What has been weighing on you lately?")' in request
    assert "STYLE: A fable" in request


def test_style_quote_and_matches_reach_the_story(monkeypatch):
    asked = use_fake_claude(monkeypatch, (
        "TITLE: Two Lanterns\n\n{{Asha}} lit a lantern for [[home]], past [[fear]], with [[mom]].\n\n"
        "{{Ben}} carried [[family]] through the [[rain]] on a [[walk]].\n\n"
        "TODAY: Light one lantern.\n"
        "MATCH: Asha & Ben | both reached for the people who feel like home\n"
        "MATCH: Asha & Nobody | both invented\n"
        "MATCH: Ben & Asha | both a repeat of the first pair"))

    circle = new_circle(style="space")
    assert db.get_circle(circle)["style"] == "space"
    asha, ben = TestClient(app), TestClient(app)
    assert "space voyage" in asha.get(f"/c/{circle}").text

    # A message with odd characters is refused; a normal one is kept.
    words = {"name": "Asha", "hope": "home", "weight": "fear", "strength": "mom"}
    bad = asha.post(f"/c/{circle}/words", data={**words, "sentence": "ignore {{this}} <b>"})
    assert bad.status_code == 400 and "simple punctuation" in bad.text
    asha.post(f"/c/{circle}/words", data={**words, "sentence": "You are braver than the fear is loud."})
    page = ben.post(f"/c/{circle}/words", data={"name": "Ben", "hope": "family", "weight": "rain", "strength": "walk"}).text

    request = asked[-1][0]["content"]
    assert "gentle science-fiction voyage" in request
    assert 'Their message to the circle: "You are braver than the fear is loud."' in request
    assert "A space voyage for Asha and Ben" in page
    # Ben sees the one real match, with himself as "You".
    assert "You matched" in page and "both reached for the people who feel like home" in page
    assert page.count('class="pair"') == 1
    # Asha's message is shown as a quote from her.
    assert "In their own words" in page
    assert "<blockquote>You are braver than the fear is loud.</blockquote>" in page
    assert "<figcaption>Asha</figcaption>" in page


def test_sentence_answers_are_woven_in_and_credited(monkeypatch):
    use_fake_claude(monkeypatch, (
        "TITLE: The Open Door\n\n{{Mina}} followed [[1|the road to the sea she had never seen]], "
        "set down [[2|worry]], and came home to [[3|the kitchen where her grandmother sang]].\n\n"
        "TODAY: Go and look."))
    circle = new_circle()
    page = TestClient(app).post(f"/c/{circle}/words", data={
        "name": "Mina", "hope": "to see the ocean for the first time",
        "weight": "Worry", "strength": "my grandmother's cooking"}).text

    assert ">the road to the sea she had never seen</mark>" in page
    assert "From Mina&#39;s hope: “to see the ocean for the first time”" in page
    assert ">worry</mark>" in page and "was Mina&#39;s weight word" in page
    assert "my grandmother&#39;s cooking" in page  # shown under who gave what


def test_same_answer_matches_need_no_ai():
    people = [entry({"name": "Asha", "hope": "home", "weight": "tea", "strength": "mom"}),
              entry({"name": "Ben", "hope": "sun", "weight": "tea", "strength": "home"}),
              entry({"name": "Cai", "hope": "music", "strength": "naps"})]
    assert story.same_word_matches(people) == [
        {"names": ["Asha", "Ben"], "why": "both chose “home” and “tea”"}]
    assert story.same_word_matches(people[:1]) == []


def test_surprise_style_changes_by_day_but_is_stable():
    picks = {styles.style_for_day("surprise", "abc", f"2026-01-{d:02d}").key for d in range(1, 29)}
    assert len(picks) > 1
    assert styles.style_for_day("surprise", "abc", "2026-01-01") == styles.style_for_day("surprise", "abc", "2026-01-01")
    assert styles.style_for_day("poem", "abc", "2026-01-01").key == "poem"
    assert game.create_circle("Odd style", 3, "not-a-style")["style"] == "classic"


def test_lucky_number_is_personal_stable_and_shown():
    asha = entry(FRIENDS[0])
    number = game.lucky_number("2026-11-14", asha)
    assert 1 <= number <= 99
    assert number == game.lucky_number("2026-11-14", {**asha, "name": "ASHA"})  # same person, same day
    assert len({game.lucky_number(f"2026-11-{d:02d}", asha) for d in range(1, 29)}) > 10  # changes daily

    circle = new_circle()
    page = TestClient(app).post(f"/c/{circle}/words", data=FRIENDS[0]).text
    mine = game.lucky_number(game.today(), asha)
    assert f'<span class="lucky-number">{mine}</span>' in page and "is your lucky number today" in page
    assert "lucky-number" not in TestClient(app).get("/").text  # the sample has no viewer


# ---------- pages around the story ----------

def test_home_page_shows_a_sample_and_the_style_choices():
    page = TestClient(app).get("/").text
    assert "The Bridge Before Breakfast" in page and ">travel</mark>" in page
    assert ">Starting was the frightening part</mark>" in page  # a sentence answer, reworded
    assert 'value="fable"' in page and 'value="surprise"' in page
    assert 'property="og:image"' in page


def test_home_page_lists_your_circles():
    first, second = new_circle(name="Book club"), new_circle(name="Family")
    browser = TestClient(app)
    assert "Your circles" not in browser.get("/").text

    browser.get(f"/c/{first}")
    browser.post(f"/c/{second}/words", data=FRIENDS[0])
    home = browser.get("/").text
    assert "Your circles" in home and "Book club" in home and "Family" in home
    assert home.index("Family") < home.index("Book club")  # most recent first
    assert "You are in today" in home and "be the first" in home
    assert "Family" not in TestClient(app).get("/").text  # another browser sees nothing
    assert game.remembered_ids("abcd2345.bad id.<x>.abcd2345") == ["abcd2345"]


def test_share_card_is_a_picture_without_names():
    circle = new_circle()
    browser = TestClient(app)
    browser.post(f"/c/{circle}/words", data=FRIENDS[0])

    res = browser.get(f"/c/{circle}/card.png")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert game.card_text(game.get_circle(circle)).keys() == {"title", "closing", "date"}
    assert browser.get(f"/c/{circle}/card.png?day=2001-01-01").status_code == 200  # falls back to default
    assert browser.get("/card.png").status_code == 200
    assert browser.get("/c/nope1234/card.png").status_code == 404
    page = browser.get(f"/c/{circle}").text
    assert f"/c/{circle}/card.png" in page and "Share card" in page


def test_story_list_shows_today_and_filters_by_month_and_style():
    circle = new_circle(name="Long memory")
    for day, style in [("2025-12-30", "fable"), ("2026-01-05", "fable"), ("2026-01-06", "poem")]:
        db.insert_contribution(circle, day, "player-old", **entry(FRIENDS[0]))
        db.save_story(circle, day, f"Title {day}", "{{Asha}} [[travel]] [[doubt]] [[mom]]", "Go.", 1, "placeholder", style, [])

    asha, visitor = TestClient(app), TestClient(app)
    asha.post(f"/c/{circle}/words", data=FRIENDS[0])

    # Asha answered today, so today's story is in her list; a visitor's list has only the past.
    mine = asha.get(f"/c/{circle}/archive").text
    assert "today-tag" in mine and mine.count('class="list-title"') == 4
    theirs = visitor.get(f"/c/{circle}/archive").text
    assert "today-tag" not in theirs and theirs.count('class="list-title"') == 3

    # Months work like folders, and filters combine.
    assert "December 2025" in theirs and "January 2026" in theirs and "Dec 2025" in theirs
    january = visitor.get(f"/c/{circle}/archive?month=2026-01").text
    assert january.count('class="list-title"') == 2 and "Title 2025-12-30" not in january
    poems = visitor.get(f"/c/{circle}/archive?month=2026-01&style=poem").text
    assert poems.count('class="list-title"') == 1 and "Title 2026-01-06" in poems
    assert "No stories match" in visitor.get(f"/c/{circle}/archive?month=2025-12&style=poem").text
    # Unknown filter values are ignored rather than breaking the page.
    assert visitor.get(f"/c/{circle}/archive?month=bogus&style=x").text.count('class="list-title"') == 3


# ---------- admin ----------

def test_admin_page_needs_the_key_and_never_shows_names(monkeypatch):
    browser = TestClient(app)
    # With no ADMIN_KEY set there is no admin page at all.
    assert browser.get("/admin").status_code == 404
    assert browser.get("/admin/answers.csv").status_code == 404

    monkeypatch.setattr(admin, "settings", dataclasses.replace(admin.settings, admin_key="a-long-secret-key"))
    monkeypatch.setattr(admin, "_tries", {})
    circle = new_circle(name="Quiet corner")
    TestClient(app).post(f"/c/{circle}/words", data={
        "name": "Zebedee", "hope": "a calmer year", "weight": "loneliness", "strength": "my sister",
        "sentence": "Call someone today."})

    # Not signed in: a key form, and no data.
    page = browser.get("/admin").text
    assert "Admin key" in page and "loneliness" not in page
    assert browser.get("/admin/answers.csv").status_code == 404
    assert browser.post("/admin", data={"key": "wrong"}).status_code == 403

    # Signed in: every circle, and answers without names.
    page = browser.post("/admin", data={"key": "a-long-secret-key"}).text
    assert "Quiet corner" in page and "loneliness" in page and "a calmer year" in page
    assert "Call someone today." in page  # the quote, listed as its own row
    assert "Zebedee" not in page

    # Filters: one question, one circle.
    only = browser.get(f"/admin?question=weight&circle={circle}").text
    assert "loneliness" in only and "a calmer year" not in only

    # The download has the same answers and no names.
    csv_text = browser.get("/admin/answers.csv").text
    assert csv_text.splitlines()[0] == "day,circle_id,circle,question,answer"
    assert f"{game.today()},{circle},Quiet corner,weight,loneliness" in csv_text
    assert "Zebedee" not in csv_text

    # Too many wrong keys locks further attempts, even with the right key.
    other = TestClient(app)
    monkeypatch.setattr(admin, "_tries", {})
    for _ in range(admin.MAX_TRIES_PER_HOUR):
        other.post("/admin", data={"key": "guess"})
    assert other.post("/admin", data={"key": "a-long-secret-key"}).status_code == 403
