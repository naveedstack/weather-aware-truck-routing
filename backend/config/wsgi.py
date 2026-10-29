"""WSGI entry point, used by Django's runserver and by Vercel's Python runtime."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
