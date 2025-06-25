# middlewares.py
import logging

from django.conf import settings
from django.http import HttpResponseForbidden

from batid.services.request import get_client_ip


class SimpleRequestLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("django.request")

    def __call__(self, request):
        self.logger.info(f"{request.method} {request.get_full_path()}")
        return self.get_response(request)


class BlockIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get client IP
        ip = get_client_ip(request)


        if ip in getattr(settings, "BLOCKED_IPS", []):
            return HttpResponseForbidden("🚫 Access Denied: Your IP is blocked.")

        return self.get_response(request)
