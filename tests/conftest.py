"""Test setup: in-memory database, no API key (placeholder stories)."""

import os

os.environ["DB_PATH"] = ":memory:"
os.environ["ANTHROPIC_API_KEY"] = ""
