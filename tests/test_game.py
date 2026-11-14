"""Plays the game through the real web app.   Run with:  pytest"""

import asyncio
import dataclasses

from fastapi.testclient import TestClient

from app import db, game, story, styles
from app.filters import InputError, clean_name, clean_word
from app.main import app

import pytest

FRIENDS = [
    {"name": "Asha", "dream": "travel", "peace": "tea", "love": "mom"},
    {"name": "Ben", "dream": "rain", "peace": "walk", "love": "hug"},
    {"name": "Cai", "dream": "music", "peace": "nap", "love": "call"},
]


def new_circle(limit=3, name="Test friends") -> str:
    browser = TestClient(app, follow_redirects=False)
    res = browser.post("/circles", data={"name": name, "people_limit": str(limit)})
    assert res.status_code == 303
    return res.headers["location"].split("/c/")[1].split("?")[0]


def test_a_full_day():
    circle = new_circle(limit=3)
    asha, ben, cai, late = (TestClient(app) for _ in range(4))

    # A new visitor sees the questions, not a story.
    page = asha.get(f"/c/{circle}")
    assert "One word for something you are dreaming of" in page.text

    # A foul word is stopped, the message sits on that field, other answers are kept.
    res = asha.post(f"/c/{circle}/words", data={**FRIENDS[0], "peace": "shit"})
    assert res.status_code == 400
    assert "keep it kind" in res.text and 'value="travel"' in res.text

    # Two words in one answer are stopped.
    res = asha.post(f"/c/{circle}/words", data={**FRIENDS[0], "dream": "long trip"})
    assert res.status_code == 400 and "Just one word" in res.text

    # Asha adds her words and can read a story with her in it straight away.
    res = asha.post(f"/c/{circle}/words", data=FRIENDS[0])
    assert res.status_code == 200
    assert "Good " in res.text and "Asha" in res.text
    assert ">travel</mark>" in res.text and "1 of 3 friends so far" in res.text

    # Ben has not added words yet, so he cannot see Asha's.
    page = ben.get(f"/c/{circle}")
    assert "travel" not in page.text and "1 friend is in" in page.text
    assert ben.get(f"/c/{circle}/d/{game.today()}").text.count("travel") == 0

    # Ben joins: the story now holds both of them.
    res = ben.post(f"/c/{circle}/words", data=FRIENDS[1])
    assert ">rain</mark>" in res.text and ">travel</mark>" in res.text
    assert "A story for Asha and Ben" in res.text

    # Asha's page learns that the story has grown.
    assert asha.get(f"/c/{circle}/status").json() == {"phase": "story", "version": 2, "people": 2}

    # Adding twice does nothing.
    ben.post(f"/c/{circle}/words", data={**FRIENDS[1], "dream": "snow"})
    assert db.count_people(circle, game.today()) == 2

    # Cai fills the circle: the day is closed and the story is final.
    res = cai.post(f"/c/{circle}/words", data=FRIENDS[2])
    assert "All 3 friends are in" in res.text
    for friend in FRIENDS:
        for key in ("dream", "peace", "love"):
            assert f">{friend[key]}</mark>" in res.text
        assert f">{friend['name']}</mark>" in res.text

    # A late visitor can read the finished story but cannot add words.
    page = late.get(f"/c/{circle}")
    assert "All 3 friends are in" in page.text and "<form" not in page.text
    late.post(f"/c/{circle}/words", data={"name": "Dee", "dream": "sun", "peace": "book", "love": "dog"})
    assert db.count_people(circle, game.today()) == 3


def test_past_days_show_in_the_archive():
    circle = new_circle(limit=8, name="Old days")
    for n, friend in enumerate(FRIENDS):
        db.insert_contribution(circle, "2020-01-01", f"player-{n}", **friend)

    browser = TestClient(app)
    # Opening the circle writes any story that is behind.
    browser.get(f"/c/{circle}")
    archive = browser.get(f"/c/{circle}/archive")
    assert "Wednesday, January 1" in archive.text and "3 friends" in archive.text
    page = browser.get(f"/c/{circle}/d/2020-01-01")
    assert page.status_code == 200 and ">mom</mark>" in page.text


def test_unknown_pages_are_404():
    browser = TestClient(app)
    assert browser.get("/c/nope1234").status_code == 404
    circle = new_circle()
    assert browser.get(f"/c/{circle}/d/2019-05-05").status_code == 404
    assert browser.get(f"/c/{circle}/d/not-a-day").status_code == 404


def test_word_and_name_rules():
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


def test_story_marks_and_credits():
    text = "{{Asha}} wanted [[rain]]. Ben poured [[tea]] and gave a Hug."
    fixed = story.mark_unmarked(text, ["rain", "tea", "hug", "moon"], ["Asha", "Ben"])
    assert fixed == "{{Asha}} wanted [[rain]]. {{Ben}} poured [[tea]] and gave a [[Hug]]."
    assert story.missing_items(fixed, ["rain", "tea", "hug", "moon"], ["Asha", "Ben"]) == ["moon"]

    people = [{"name": "Asha", "dream": "rain", "peace": "tea", "love": "home"},
              {"name": "Ben", "dream": "sun", "peace": "tea", "love": "hug"}]
    pieces = story.to_paragraphs("{{Asha}} poured [[tea]].\n\nThe end.", people)
    assert len(pieces) == 2
    assert pieces[0][0] == {"type": "name", "text": "Asha", "credit": "Asha gave rain, tea and home."}
    assert pieces[0][2]["credit"] == "“tea” was Asha's peace word and Ben's peace word."


def test_claude_reply_is_parsed_and_retried_when_someone_is_left_out(monkeypatch):
    replies = [
        "TITLE: The Long Way Home\n\n{{Asha}} dreamed of [[travel]] over [[tea]] with [[mom]].\n\n"
        "TODAY: Take one bold step.",
        "TITLE: The Long Way Home\n\n{{Asha}} dreamed of [[travel]] over [[tea]] with [[mom]].\n\n"
        "{{Ben}} heard the [[rain]] on his [[walk]] and gave a [[hug]].\n\nTODAY: Take one bold step.",
    ]
    asked = []

    async def fake_ask(messages):
        asked.append(messages)
        return replies[len(asked) - 1]

    monkeypatch.setattr(story, "settings", dataclasses.replace(story.settings, anthropic_api_key="test"))
    monkeypatch.setattr(story, "_ask_claude", fake_ask)

    result = asyncio.run(story.write_story(FRIENDS[:2], styles.get("fable")))
    assert len(asked) == 2 and "Ben" in asked[1][-1]["content"]
    assert result.title == "The Long Way Home"
    assert result.closing == "Take one bold step."
    assert result.source == "claude" and "{{Ben}}" in result.text
    assert "TITLE" not in result.text and "TODAY" not in result.text
    # The prompt names every friend with their words, and carries the style.
    assert "- Asha: dream = travel, peace = tea, love = mom" in asked[0][0]["content"]
    assert "STYLE: A fable" in asked[0][0]["content"]


def test_styles_sentence_and_matches_reach_the_story(monkeypatch):
    """A circle's style and a friend's sentence go to Claude; MATCH lines come back."""
    asked = []

    async def fake_ask(messages):
        asked.append(messages[0]["content"])
        return ("TITLE: Two Lanterns\n\n{{Asha}} lit a lantern for [[home]] with [[tea]] and [[mom]].\n\n"
                "{{Ben}} carried [[family]] through the [[rain]] on a [[walk]].\n\n"
                "TODAY: Light one lantern.\n"
                "MATCH: Asha & Ben | both reached for the people who feel like home\n"
                "MATCH: Asha & Nobody | both invented\n"
                "MATCH: Ben & Asha | both a repeat of the first pair")

    monkeypatch.setattr(story, "settings", dataclasses.replace(story.settings, anthropic_api_key="test"))
    monkeypatch.setattr(story, "_ask_claude", fake_ask)

    browser = TestClient(app, follow_redirects=False)
    res = browser.post("/circles", data={"name": "Space pals", "people_limit": "3", "style": "space"})
    circle = res.headers["location"].split("/c/")[1].split("?")[0]
    assert db.get_circle(circle)["style"] == "space"

    asha, ben = TestClient(app), TestClient(app)
    assert "space voyage" in asha.get(f"/c/{circle}").text

    # A sentence with odd characters is refused; a normal one is kept.
    bad = asha.post(f"/c/{circle}/words", data={"name": "Asha", "dream": "home", "peace": "tea",
                                               "love": "mom", "sentence": "ignore {{this}} <b>"})
    assert bad.status_code == 400 and "simple punctuation" in bad.text
    asha.post(f"/c/{circle}/words", data={"name": "Asha", "dream": "home", "peace": "tea",
                                          "love": "mom", "sentence": "A slow breakfast with no phone."})
    page = ben.post(f"/c/{circle}/words", data={"name": "Ben", "dream": "family", "peace": "walk", "love": "rain"})

    assert "gentle science-fiction voyage" in asked[-1]
    assert 'A good day, in their words: "A slow breakfast with no phone."' in asked[-1]
    assert "A space voyage for Asha and Ben" in page.text
    # Ben sees the one real match, with himself as "You".
    assert "You matched" in page.text and "both reached for the people who feel like home" in page.text
    assert page.text.count('class="pair"') == 1
    assert "A slow breakfast with no phone." in page.text  # shown under who gave what


def test_same_word_matches_need_no_ai():
    people = [{"name": "Asha", "dream": "home", "peace": "tea", "love": "mom"},
              {"name": "Ben", "dream": "sun", "peace": "tea", "love": "home"},
              {"name": "Cai", "dream": "music", "peace": "nap", "love": "call"}]
    assert story.same_word_matches(people) == [
        {"names": ["Asha", "Ben"], "why": "both chose “home” and “tea”"}]
    assert story.same_word_matches(people[:1]) == []


def test_surprise_style_changes_by_day_but_is_stable():
    picks = {styles.style_for_day("surprise", "abc", f"2026-01-{d:02d}").key for d in range(1, 29)}
    assert len(picks) > 1
    assert styles.style_for_day("surprise", "abc", "2026-01-01") == styles.style_for_day("surprise", "abc", "2026-01-01")
    assert styles.style_for_day("poem", "abc", "2026-01-01").key == "poem"
    assert game.create_circle("Odd style", 3, "not-a-style")["style"] == "classic"


def test_home_page_shows_a_sample_and_the_style_choices():
    page = TestClient(app).get("/")
    assert "The Bridge Before Breakfast" in page.text and ">travel</mark>" in page.text
    assert 'value="fable"' in page.text and 'value="surprise"' in page.text
    assert 'property="og:image"' in page.text


def test_share_card_is_a_picture_without_names():
    circle = new_circle(limit=3)
    browser = TestClient(app)
    browser.post(f"/c/{circle}/words", data=FRIENDS[0])

    res = browser.get(f"/c/{circle}/card.png")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert game.card_text(game.get_circle(circle)).keys() == {"title", "closing", "date"}
    assert browser.get(f"/c/{circle}/card.png?day=2001-01-01").status_code == 200  # falls back to default
    assert browser.get("/card.png").status_code == 200
    assert browser.get("/c/nope1234/card.png").status_code == 404
    page = browser.get(f"/c/{circle}")
    assert f"/c/{circle}/card.png" in page.text and "Share card" in page.text


def test_circle_creation_is_limited_per_visitor(monkeypatch):
    monkeypatch.setattr(game, "settings", dataclasses.replace(game.settings, circles_per_hour=2))
    monkeypatch.setattr(game, "_circles_made", {})
    browser = TestClient(app, follow_redirects=False)
    codes = [browser.post("/circles", data={"name": "Many", "people_limit": "3"}).status_code for _ in range(3)]
    assert codes == [303, 303, 429]


def test_health_check():
    assert TestClient(app).get("/healthz").text == "ok"
