# Story Board

**A few words each. One story a day.**

Friends share one link. Each morning a friend answers three small questions,
each with a word or a short sentence (and, if they like, a message to the circle). Claude then writes a
short story of **hope, love and boldness** in which every friend appears by
name, in a good light, alongside their words. The friend reads it straight
away, before the day begins, and the story grows as more friends add theirs.

Each circle picks a **style** (heartfelt, fable, adventure, space, poem, or a
surprise each day). The story page also shows each friend's message as a
**quote** from them, which friends **matched** on a similar idea, a **lucky
number** for each friend (made from their own words and the date, for fun), and
a **share card**: a picture of the closing line with no names or words on it.

| Question | What it gives the story |
|---|---|
| What are you hoping for right now? | **Hope**: what the story reaches for |
| What has been weighing on you lately? (optional) | **Weight**: what the friend is carrying |
| Who or what is getting you through? | **Strength**: what meets them in the middle |
| What would you say to a friend who feels the same? (optional) | Shown as a **quote** from them |

Story Board is also a small research project: the person who runs it can read
answers from every circle, **without names**, to understand what people hope
for and struggle with. The form says so, and `/privacy` explains it in plain words.

## Rules of the game

- A **circle** is a group of friends with its own link (`/c/<id>`). The link never changes.
- Each person adds their first name and answers the questions **once per day**.
  An answer is one word or a short sentence (up to 80 characters).
- Foul language is blocked on the spot and the person is asked to try again.
- As soon as you add your words, the story is rewritten to include you and you can read it.
- Friends who have not added words yet **cannot see** today's story or anyone's words.
- When the circle's limit is reached (3 to 12 friends, default 8) the day is closed
  and the story is final. Everyone with the link can then read it.
- At midnight a new day starts. Every story is kept under **Stories**, grouped by
  month, with filters for month and style. Today's story is listed there too for
  anyone who may read it.
- The home page lists **Your circles**: the circles this browser has opened.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env            # Windows: Copy-Item .env.example .env
uvicorn app.main:app --reload   # http://localhost:8000
```

The key is read from an environment variable named `STORY_KEY`
(`export STORY_KEY=...`, or `$env:STORY_KEY="..."` in PowerShell), or you can
paste it into `.env` directly.

Without an API key the game still works end to end and writes a plain
placeholder story, which is handy for testing.

```bash
pytest                          # plays a full day automatically
```

## Put it online (Render + Neon, both free)

Free hosts wipe local files, so online the app keeps its data in Postgres.

1. **Database:** create a free project at neon.com and copy its connection
   string (it starts with `postgresql://`).
2. **App:** at render.com choose **New > Blueprint** and pick this repo. Render
   reads `render.yaml` and asks for two values: `ANTHROPIC_API_KEY` (your Claude
   key) and `DATABASE_URL` (the Neon string).
3. Open the `onrender.com` address Render gives you. The tables are created on
   first start.

On the free plan the app sleeps after 15 minutes without visitors; the next
visitor waits about a minute while it wakes.

### Settings (`.env`)

| Name | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Your Claude key. Empty means placeholder stories. |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Which Claude model writes the story. |
| `STORY_TIMEZONE` | `America/New_York` | The day rolls over at midnight here. |
| `DB_PATH` | `data/stories.db` | Where the local SQLite file is stored. |
| `DATABASE_URL` | empty | A Postgres connection string. When set, Postgres is used instead of SQLite. |
| `CIRCLES_PER_HOUR` | `10` | How many circles one visitor may create per hour. |
| `ADMIN_KEY` | empty | A long secret (12+ characters) that opens `/admin`. Empty means no admin page. |
| `CONTACT_EMAIL` | empty | Shown on the privacy page for removal requests. |

`STORY_KEY` also works as a second name for `ANTHROPIC_API_KEY`.

The `.env` file is ignored by git. Never commit your key.

## Repo structure

Everything is Python except one stylesheet and one small script for the browser.

```
fun-story-board/
├── app/
│   ├── main.py             web server: every page route (start here)
│   ├── game.py             the rules: who sees what, when the story is rewritten
│   ├── story.py            the story prompt, the Claude call, and the checks on the result
│   ├── styles.py           the story styles a circle can choose (add one here)
│   ├── card.py             draws the share card picture
│   ├── sample.py           the sample story shown on the home page
│   ├── filters.py          one-word check and foul-word filter
│   ├── questions.py        the daily questions (edit the wording here)
│   ├── admin.py            the admin page: all circles, answers without names, CSV download
│   ├── db.py               tables and every SQL query (SQLite locally, Postgres online)
│   ├── config.py           settings and environment variables
│   ├── templates/          the pages, drawn in Python with Jinja2
│   │   ├── base.html       shared frame: header, link-preview text
│   │   ├── home.html       sample story + create a circle
│   │   ├── words.html      the three questions, name, optional message
│   │   ├── writing.html    "writing you into the story…"
│   │   ├── story.html      the story page (today and past days)
│   │   ├── _story.html     the story, quotes and matches (shared with the home page sample)
│   │   ├── archive.html    all stories by month, with filters
│   │   ├── privacy.html    who can read what
│   │   ├── admin.html      the admin page (and admin_login.html, its key form)
│   │   └── problem.html    not-found page
│   └── static/
│       ├── css/style.css   all styling
│       ├── fonts/          Lora (open licence), used to draw the share card
│       └── js/story.js     tap-a-word credits, auto-open when written, share buttons
├── tests/
│   ├── conftest.py         test settings (in-memory database, no API key)
│   └── test_game.py        full-day playthrough + checks for filters and story parsing
├── requirements.txt
├── render.yaml             how Render runs the app
├── .env.example            template for your settings
└── README.md
```

### Where to change things

| To change... | Edit |
|---|---|
| The tone, themes or length of the story | `SYSTEM_PROMPT` and `target_length` in `app/story.py` |
| The questions, or the message prompt | `app/questions.py` |
| How the lucky number is worked out | `lucky_number` in `app/game.py` |
| The story styles | `app/styles.py` |
| The sample on the home page | `app/sample.py` |
| How the share card looks | `app/card.py` |
| Which words are blocked or allowed | `ALLOWED_WORDS` in `app/filters.py` |
| Circle size limits, timezone, model | `app/config.py` or `.env` |
| How the story page looks | `app/templates/story.html` and the "story reading view" part of `style.css` |

### How a request flows

```
phone: form in templates/words.html
   │  POST /c/{id}/words   (name, hope, weight, strength, quote)
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

1. `story.py` gives every answer a number and sends each friend's name, answers
   and optional message, plus the circle's style, with the system prompt.
2. The reply must mark the place that carries each answer as `[[3|words in the
   story]]` (a one-word answer exactly, a sentence reworded) and names as `{{Name}}`, with a
   `TITLE:` line, a closing `TODAY:` line, and optional `MATCH:` lines naming two
   friends whose words point to a similar idea.
3. Small slips are repaired in Python (`tidy_marks`). If an answer or name is
   still missing, Claude is asked once to rewrite the story.
4. `MATCH:` lines are kept only if they name two real friends. If Claude gives
   none, friends who chose the very same word are matched in Python.
5. The page turns the marks into highlights and "whose word is this" credits.

### Data model

| Table | One row per | Key columns |
|---|---|---|
| `circles` | friend group | `id`, `name`, `people_limit`, `style` |
| `contributions` | person per day | `id`, `circle_id`, `day`, `player_id`, `name`, `sentence` (their quote) |
| `answers` | answer | `contribution_id`, `question` (e.g. `hope`), `text` |
| `stories` | circle per day | `circle_id`, `day`, `title`, `text`, `closing`, `people`, `source`, `style`, `matches` |

`stories.people` is how many friends that version includes. When it is lower
than the number of contributions, the story is behind and gets rewritten.

Answers have their own table so the questions can change without changing the
database. Each answer remembers its question key, and retired questions stay
listed in `questions.py` so old stories keep their labels and colours.

## Admin page

Set `ADMIN_KEY` in the host's environment settings, then open `/admin` and
enter the key. It shows every circle with how much it is used, and every answer
with its question, day and circle but **no names**. Filter by question or
circle, or download everything as a CSV file. The "stories" link opens a
circle's story list as its members see it.

## Privacy notes

- The form tells every player that the person running the app can read answers
  and studies them without names. `/privacy` has the full explanation.

- First names, words and the optional message are sent to the Claude API so
  each friend can be a character in the story. Nothing else about a person is sent.
- The share card and the link preview show only the title and closing line.
- No accounts. A random id in a browser cookie keeps it to one entry per person per day.
  A second cookie remembers which circles the browser has opened.

## Not built yet

- Changing a circle's style after it is created
- A morning reminder
- Circle streaks and a monthly keepsake
