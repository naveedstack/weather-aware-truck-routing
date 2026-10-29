"""Settings for the test suite: fixed values, so tests never depend on (or see) backend/.env."""

import os

# Set before importing settings: load_dotenv() never overrides variables that already exist.
os.environ.update(
    DJANGO_SECRET_KEY="test-only-secret-key",
    DJANGO_DEBUG="false",
    DJANGO_ALLOWED_HOSTS="testserver",
    TOMTOM_API_KEY="test-key",
)

from .settings import *  # noqa: F403
