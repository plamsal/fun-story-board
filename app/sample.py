"""The sample story on the home page, so visitors see what they will get.

It is drawn with the same code and template as a real story.
Edit the text here to change the sample.
"""

from . import game

PEOPLE = [
    {"name": "Asha", "dream": "travel", "peace": "tea", "love": "mom", "sentence": ""},
    {"name": "Ben", "dream": "rain", "peace": "walk", "love": "hug", "sentence": ""},
    {"name": "Cai", "dream": "music", "peace": "nap", "love": "call", "sentence": ""},
]

SAVED = {
    "day": "2026-01-01",
    "title": "The Bridge Before Breakfast",
    "text": (
        "For months a packed bag had waited by {{Asha}}'s door, a promise of [[travel]] made "
        "and postponed. This morning, over a cup of [[tea]], came the memory of [[mom]] "
        "saying go on, then. {{Asha}} picked up the bag.\n\n"
        "At the corner stood {{Ben}}, out in the [[rain]] with no umbrella and a wide grin. "
        "A morning [[walk]], {{Ben}} said, makes the world look more possible. There was a "
        "[[hug]] that smelled of wet wool, and then two sets of footsteps instead of one.\n\n"
        "They heard {{Cai}} before they saw anyone: [[music]] from an open window, a song "
        "almost finished. The last verse had arrived during a [[nap]]. “I'm playing it for "
        "people tonight,” {{Cai}} said. “Out loud.” One [[call]] first, to the friend who "
        "had always believed it would happen.\n\n"
        "Then three friends crossed the bridge together, each carrying something small and brave."
    ),
    "closing": "The bold thing gets lighter the moment you pick it up.",
    "people": 3,
    "source": "sample",
    "style": "classic",
    "matches": [{"names": ["Asha", "Ben"], "why": "both dreamed of getting out the door"}],
}


def sample_story() -> dict:
    return game.build_story_view(SAVED, PEOPLE)
