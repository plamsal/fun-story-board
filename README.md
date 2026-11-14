# Story Board

**Three words each. One story a day.**

Friends share one link. Each morning a friend answers three small questions
with one word each. Claude then writes a short story of **hope, love and
boldness** in which every friend appears by name, in a good light, alongside
their words. The friend reads it straight away, before the day begins, and the
story grows as more friends add theirs.

| Question | Feeds the story's... |
|---|---|
| One word for something you are dreaming of | **Dream**: the hope it reaches for |
| One word for what brings you peace | **Peace**: the calm that gives strength |
| One word for someone or something you love | **Love**: the warmth it lands on |

## Rules of the game

- A **circle** is a group of friends with its own link (`/c/<id>`). The link never changes.
- Each person adds their first name and three words **once per day**.
- Foul words are blocked on the spot and the person is asked for another word.
- As soon as you add your words, the story is rewritten to include you and you can read it.
- Friends who have not added words yet **cannot see** today's story or anyone's words.
- When the circle's limit is reached (3 to 12 friends, default 8) the day is closed
  and the story is final. Everyone with the link can then read it.
- At midnight a new day starts. Finished days are kept under **Past stories**.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then put your Claude API key in .env
uvicorn app.main:app --reload   # http://localhost:8000
```

Without an API key the game still works end to end and writes a plain
placeholder story, which is handy for testing.

```bash
pytest                          # plays a full day automatically
```

### Settings (`.env`)

| Name | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Your Claude key. Empty means placeholder stories. |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Which Claude model writes the story. |
| `STORY_TIMEZONE` | `America/New_York` | The day rolls over at midnight here. |
| `DB_PATH` | `data/stories.db` | Where the SQLite file is stored. |

The `.env` file is ignored by git. Never commit your key.

## Repo structure

Everything is Python except one stylesheet and one small script for the browser.

```
fun-story-board/
├── app/
│   ├── main.py             web server: every page route (start here)
│   ├── game.py             the rules: who sees what, when the story is rewritten
│   ├── story.py            the story prompt, the Claude call, and the checks on the result
│   ├── filters.py          one-word check and foul-word filter
│   ├── questions.py        the three daily questions (edit the wording here)
│   ├── db.py               SQLite tables and every SQL query
│   ├── config.py           settings and environment variables
│   ├── templates/          the pages, drawn in Python with Jinja2
│   │   ├── base.html       shared frame: header, link-preview text
│   │   ├── home.html       create a circle
│   │   ├── words.html      the three questions + name
│   │   ├── writing.html    "writing you into the story…"
│   │   ├── story.html      the reading view (today and past days)
│   │   ├── archive.html    list of past stories
│   │   └── problem.html    not-found page
│   └── static/
│       ├── css/style.css   all styling
│       └── js/story.js     tap-a-word credits, auto-open when written, share button
├── tests/
│   ├── conftest.py         test settings (in-memory database, no API key)
│   └── test_game.py        full-day playthrough + checks for filters and story parsing
├── requirements.txt
├── .env.example            template for your settings
└── README.md
```

### Where to change things

| To change... | Edit |
|---|---|
| The tone, themes or length of the story | `SYSTEM_PROMPT` and `target_length` in `app/story.py` |
| The questions | `app/questions.py` |
| Which words are blocked or allowed | `ALLOWED_WORDS` in `app/filters.py` |
| Circle size limits, timezone, model | `app/config.py` or `.env` |
| How the story page looks | `app/templates/story.html` and the "story reading view" part of `style.css` |

### How a request flows

```
phone: form in templates/words.html
   │  POST /c/{id}/words   (name, dream, peace, love)
   ▼
app/main.py ──► app/game.py ──► app/filters.py   (clean + block foul words)
                    │
                    ├──► app/db.py               (save the words)
                    │
                    └──► app/story.py            (rewrite the story with Claude)
                              │
                              └──► app/db.py     (save the new version)
   ▼
phone: templates/writing.html, then templates/story.html
```

### What a visitor sees

```
form ──(adds words)──► writing ──(story includes them)──► story
                                                            │
                          a friend joins later ─────────────┘  "the story has grown"
```

`game.today_view()` decides the phase; the templates only draw it.

### How the story is checked

1. `story.py` sends each friend's name and three words with the system prompt.
2. The reply must mark words as `[[word]]` and names as `{{Name}}`, with a
   `TITLE:` line and a closing `TODAY:` line.
3. If any word or name is missing, Claude is asked once to rewrite it.
4. The page turns the marks into highlights and "whose word is this" credits.

### Data model

| Table | One row per | Key columns |
|---|---|---|
| `circles` | friend group | `id`, `name`, `people_limit` |
| `contributions` | person per day | `circle_id`, `day`, `player_id`, `name`, `dream`, `peace`, `love` |
| `stories` | circle per day | `circle_id`, `day`, `title`, `text`, `closing`, `people`, `source` |

`stories.people` is how many friends that version includes. When it is lower
than the number of contributions, the story is behind and gets rewritten.

## Privacy notes

- First names and words are sent to the Claude API so each friend can be a
  character in the story. Nothing else about a person is sent.
- No accounts. A random id in a browser cookie keeps it to one entry per person per day.

## Not built yet

- Hosting (the SQLite file needs a host with a persistent disk, or a swap to a hosted database in `db.py`)
- A picture for link previews on Facebook and LinkedIn (titles and descriptions already work)
- Rate limiting on circle creation
- A morning reminder
