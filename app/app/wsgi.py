"""
WSGI config for app project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from django.urls import get_resolver

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

application = get_wsgi_application()

# Load all the views at startup (gunicorn --preload): the container accepts requests only once the app is ready.
get_resolver().url_patterns
