"""Story styles a circle can choose.

    key     saved with the circle and the story
    label   shown on the page ("A fable for Asha and Ben")
    blurb   one line shown when picking a style
    guide   what the story writer is told

Add a style by adding an entry here; nothing else needs to change.
"""

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Style:
    key: str
    label: str
    article: str  # "a" or "an", for "A fable for..."
    blurb: str
    guide: str


STYLES = [
    Style(
        key="classic",
        label="story",
        article="a",
        blurb="Heartfelt: a warm, true-to-life moment",
        guide="A warm, true-to-life scene set on an ordinary morning. Small, concrete "
              "details. It could have happened today.",
    ),
    Style(
        key="fable",
        label="fable",
        article="a",
        blurb="Fable: a timeless tale, as if told by a fire",
        guide="A fable or folk tale, told as if beside a fire: a village, a road, a river, "
              "seasons. Simple, musical sentences. The friends stay people (not animals) "
              "and keep their names. Do not state a moral.",
    ),
    Style(
        key="adventure",
        label="adventure",
        article="an",
        blurb="Adventure: a quest with a map and a brave turn",
        guide="A small adventure: a map, a path, an obstacle and a brave turn. Brisk and "
              "bright, with a little humour. Nobody is in real danger and nobody is hurt.",
    ),
    Style(
        key="space",
        label="space voyage",
        article="a",
        blurb="Space: a voyage among the stars",
        guide="A gentle science-fiction voyage: a small ship, a quiet crew, stars outside "
              "the window. Wonder over gadgets. The friends are the crew.",
    ),
    Style(
        key="poem",
        label="poem",
        article="a",
        blurb="Poem: free verse in a few short stanzas",
        guide="A free-verse poem instead of prose: 3 or 4 stanzas separated by blank lines, "
              "each of 3 to 6 short lines, one line per row. No rhyme needed. Every friend "
              "still appears by name.",
    ),
]

BY_KEY = {style.key: style for style in STYLES}

SURPRISE = "surprise"
SURPRISE_BLURB = "Surprise me: a different style each day"

# What the create-a-circle form offers: (key, blurb)
CHOICES = [(style.key, style.blurb) for style in STYLES] + [(SURPRISE, SURPRISE_BLURB)]


def is_valid(key: str | None) -> bool:
    return key in BY_KEY or key == SURPRISE


def style_for_day(circle_style: str, circle_id: str, day: str) -> Style:
    """The style to write in today. "Surprise me" picks one per circle per day."""
    if circle_style in BY_KEY:
        return BY_KEY[circle_style]
    digest = hashlib.sha256(f"{circle_id}|{day}".encode()).digest()
    return STYLES[digest[0] % len(STYLES)]


def get(key: str) -> Style:
    return BY_KEY.get(key, BY_KEY["classic"])
