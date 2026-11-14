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
    # Database. If DATABASE_URL is set (on the host), Postgres is used.
    # Otherwise a local SQLite file is used (":memory:" in the tests).
    database_url: str = os.getenv("DATABASE_URL", "")
    db_path: str = os.getenv("DB_PATH", "data/stories.db")

    # The "day" rolls over at midnight in this timezone.
    time_zone: str = os.getenv("STORY_TIMEZONE", "America/New_York")

    # How many friends write one day's story (chosen per circle).
    default_people_limit: int = 8
    min_people_limit: int = 3
    max_people_limit: int = 12

    # How many circles one visitor (IP address) may create per hour.
    circles_per_hour: int = int(os.getenv("CIRCLES_PER_HOUR", "10"))

    # A long secret that opens the admin page (/admin). Empty = no admin page.
    admin_key: str = os.getenv("ADMIN_KEY", "")

    # Shown on the privacy page so people can ask for their answers to be removed.
    contact_email: str = os.getenv("CONTACT_EMAIL", "")

    # Claude API key: ANTHROPIC_API_KEY, or STORY_KEY as a second name for it.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY") or os.getenv("STORY_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    # After a failed story attempt, wait this long before trying again.
    retry_after_seconds: int = 30


settings = Settings()
