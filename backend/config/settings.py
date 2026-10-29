"""Django settings. Everything that differs between machines comes from environment variables.

Locally they are read from backend/.env (see .env.example); on Vercel they are set in the
project's Environment Variables.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # does nothing when the file is absent, as on Vercel


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY (see backend/.env.example).")
    SECRET_KEY = "insecure-local-development-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if os.environ.get("VERCEL"):
    # Any of the project's vercel.app names (production aliases, previews). Vercel only routes a
    # host to this deployment if it belongs to the project, and the API builds no absolute URLs.
    ALLOWED_HOSTS.append(".vercel.app")
    # The production domain, which is a custom domain when the project has one.
    if os.environ.get("VERCEL_PROJECT_PRODUCTION_URL"):
        ALLOWED_HOSTS.append(os.environ["VERCEL_PROJECT_PRODUCTION_URL"])
if DEBUG:
    ALLOWED_HOSTS += ["localhost", "127.0.0.1"]

# The API needs no database, sessions, admin or user accounts.
INSTALLED_APPS = [
    "rest_framework",
    "trips",
]
DATABASES: dict = {}

# No GZipMiddleware: Vercel's CDN compresses responses itself, with Brotli when the browser allows.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# Behind Vercel's proxy the original scheme arrives in X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Per-process memory cache. On Vercel each function instance has its own copy, so the app never
# relies on it to stay within Open-Meteo's limits; it only saves repeat calls.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "trip-planner",
        "TIMEOUT": 3600,
        "OPTIONS": {"MAX_ENTRIES": 5000},
    }
}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "trips.views.api_exception_handler",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {"trips": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}

TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
