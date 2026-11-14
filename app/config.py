"""Central settings.

Everything that can be tuned lives here. Anything secret is read from the
environment (the .env file on your machine), never hard-coded.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # reads .env if it exists; real environment variables win


@dataclass(frozen=True)
class Settings:
    # Where the SQLite file lives (":memory:" is used by the tests).
    db_path: str = os.getenv("DB_PATH", "data/stories.db")

    # The "day" rolls over at midnight in this timezone.
    time_zone: str = os.getenv("STORY_TIMEZONE", "America/New_York")

    # How many friends write one day's story (chosen per circle).
    default_people_limit: int = 8
    min_people_limit: int = 3
    max_people_limit: int = 12

    # Claude API
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    # After a failed story attempt, wait this long before trying again.
    retry_after_seconds: int = 30


settings = Settings()
