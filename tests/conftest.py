"""Test setup: no API key (placeholder stories) and a throwaway database.

By default the tests use an in-memory SQLite database. To run the same tests
against Postgres, set TEST_DATABASE_URL to an empty test database:

    TEST_DATABASE_URL=postgresql://user:pass@localhost/storytest pytest
"""

import os

os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["STORY_KEY"] = ""
os.environ["CIRCLES_PER_HOUR"] = "1000"
os.environ["DB_PATH"] = ":memory:"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")
