"""The three daily questions.

Each answer is ONE word, and each question feeds a different part of the story.
Edit the wording here; nothing else needs to change.

    key    column name in the database, and the colour used on the page
    label  short tag shown above the question
    ask    what the player sees
    role   how the story writer is told to use these words
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    key: str
    label: str
    ask: str
    role: str


QUESTIONS = [
    Question(
        key="dream",
        label="Dream",
        ask="One word for something you are dreaming of",
        role="the hope the story reaches for",
    ),
    Question(
        key="peace",
        label="Peace",
        ask="One word for what brings you peace",
        role="the calm that gives the characters strength",
    ),
    Question(
        key="love",
        label="Love",
        ask="One word for someone or something you love",
        role="the warmth the story lands on",
    ),
]

KEYS = [q.key for q in QUESTIONS]
