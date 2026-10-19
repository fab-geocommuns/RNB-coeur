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

# Import every view module now: with gunicorn --preload this runs once in the master,
# before the workers fork, so the port only opens when the app is fully loaded.
get_resolver().url_patterns
