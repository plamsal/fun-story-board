"""The sample story on the home page, so visitors see what they will get.

It is drawn with the same code and template as a real story.
Edit the text here to change the sample. The numbers in [[3|...]] are the
answers' numbers, counted in order: Asha's are 1-3, Ben's 4-6, Cai's 7-8.
"""

from . import game

PEOPLE = [
    {"name": "Asha", "sentence": "Go before you feel ready. Ready comes later.",
     "answers": {"hope": "travel", "weight": "being afraid to start", "strength": "mom"}},
    {"name": "Ben", "sentence": "",
     "answers": {"hope": "a fresh start", "weight": "money worries", "strength": "long walks"}},
    {"name": "Cai", "sentence": "Play the song even if your hands shake.",
     "answers": {"hope": "music", "strength": "the friend who always believed in me"}},
]

SAVED = {
    "day": "2026-01-01",
    "title": "The Bridge Before Breakfast",
    "text": (
        "For months a packed bag had waited by {{Asha}}'s door, a promise of [[1|travel]] made "
        "and postponed. [[2|Starting was the frightening part]]. This morning, over a cup of "
        "tea, came the memory of [[3|mom]] saying go on, then. {{Asha}} picked up the bag.\n\n"
        "At the corner stood {{Ben}}, out in the rain with no umbrella and a wide grin. "
        "[[5|The bills had not gone anywhere]], {{Ben}} admitted, but [[6|a long walk]] made "
        "the world look possible again, and today felt like [[4|the first page of something "
        "new]]. Two sets of footsteps now, instead of one.\n\n"
        "They heard {{Cai}} before they saw anyone: [[7|music]] from an open window, a song "
        "almost finished. \u201cI'm playing it for people tonight,\u201d {{Cai}} said. \u201cOut loud.\u201d "
        "One call first, to [[8|the friend who had always believed it would happen]].\n\n"
        "Then three friends crossed the bridge together, each carrying something small and brave."
    ),
    "closing": "The bold thing gets lighter the moment you pick it up.",
    "people": 3,
    "source": "sample",
    "style": "classic",
    "matches": [{"names": ["Asha", "Ben"], "why": "both are standing at the start of something"}],
}


def sample_story() -> dict:
    return game.build_story_view(SAVED, PEOPLE)
