"""The questions friends answer each day.

Each answer is one word or a short sentence, and each question feeds a
different part of the story. Edit the wording here; nothing else needs to change.

    key       saved with every answer, and the colour used on the page
    label     short tag shown above the question
    ask       what the player sees
    role      how the story writer is told to use these answers
    optional  True if the friend may leave it empty

Questions can change over time. Answers are stored one row each with their
question key (see the `answers` table in db.py), so old stories keep working.
When you retire a question, move it to RETIRED so its old answers still have
a label and a colour.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    key: str
    label: str
    ask: str
    role: str
    optional: bool = False
    hint: str = "A word or a short sentence"


# Asked today, in this order.
QUESTIONS = [
    Question(
        key="hope",
        label="Hope",
        ask="What are you hoping for right now?",
        role="what the story reaches for, and where it ends: a bold step toward it",
    ),
    Question(
        key="weight",
        label="Weight",
        ask="What has been weighing on you lately?",
        role="what the friend is carrying when the story begins. Handle it gently",
        optional=True,
        hint="A word or a short sentence. Skip it if you would rather not say.",
    ),
    Question(
        key="strength",
        label="Strength",
        ask="Who or what is getting you through?",
        role="the love and steadiness that meets the friend in the middle of the story",
    ),
]

# Asked in earlier versions. Kept so that older stories still display.
RETIRED = [
    Question(key="dream", label="Dream", ask="Something you are dreaming of", role=""),
    Question(key="peace", label="Peace", ask="Something that brings you peace", role=""),
    Question(key="love", label="Love", ask="Someone or something you love", role=""),
]

KEYS = [q.key for q in QUESTIONS]
ALL = {q.key: q for q in QUESTIONS + RETIRED}
ORDER = {key: i for i, key in enumerate(ALL)}  # display order for any mix of keys


def label(key: str) -> str:
    return ALL[key].label if key in ALL else key.capitalize()


def in_order(answers: dict[str, str]) -> dict[str, str]:
    """The same answers, sorted into question order."""
    return dict(sorted(answers.items(), key=lambda item: ORDER.get(item[0], 99)))


# The friend's own message to the circle, shown on the story page as a quote
# from them. Optional. (It is stored in the `sentence` column of contributions.)
QUOTE_ASK = "What would you say to a friend who feels the same?"
QUOTE_HINT = "Your circle will read this as a quote from you."
