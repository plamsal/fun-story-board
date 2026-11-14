"""Input checks: "is this really one word?" and "is it a foul word?".

Each clean_* function returns the cleaned value or raises InputError with a
friendly message that is shown under the field.
"""

import re

from better_profanity import profanity

# The word list is strict. These everyday words are allowed on purpose.
ALLOWED_WORDS = ["god", "gay", "queer", "pot", "weed", "strip", "knob", "virgin", "hell"]

profanity.load_censor_words(whitelist_words=ALLOWED_WORDS)

# One word: letters (any language) with optional ' or - inside. Max 20 chars.
WORD_RE = re.compile(r"^[^\W\d_](?:[^\W\d_]|['’-]){0,19}$")
# Name: letters, spaces, dots, apostrophes, hyphens. Max 24 chars.
NAME_RE = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ .'’-]){0,23}$")
# Circle name: also allows numbers and light punctuation. Max 40 chars.
CIRCLE_RE = re.compile(r"^[^\W_](?:[^\W_]|[ .,'’&!-]){0,39}$")


class InputError(ValueError):
    """A problem with something a person typed."""


def is_foul(text: str) -> bool:
    return profanity.contains_profanity(text)


def clean_word(raw: str | None) -> str:
    word = (raw or "").strip().lower()
    if not word:
        raise InputError("Please add a word.")
    if re.search(r"\s", word):
        raise InputError("Just one word, please.")
    if not WORD_RE.match(word):
        raise InputError("Use a single word with letters only (up to 20).")
    if is_foul(word):
        raise InputError("Let's keep it kind. Try a different word.")
    return word


def clean_name(raw: str | None) -> str:
    name = " ".join((raw or "").split())
    if not name:
        raise InputError("Please add your name.")
    if not NAME_RE.match(name):
        raise InputError("Names can use letters and spaces (up to 24).")
    if is_foul(name):
        raise InputError("Let's keep it kind. Try a different name.")
    return name


def clean_circle_name(raw: str | None) -> str:
    name = " ".join((raw or "").split())
    if not name:
        raise InputError("Please name your circle.")
    if not CIRCLE_RE.match(name):
        raise InputError("Circle names can use letters, numbers and spaces (up to 40).")
    if is_foul(name):
        raise InputError("Let's keep it kind. Try a different name.")
    return name
