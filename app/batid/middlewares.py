# middlewares.py
import logging

class SimpleRequestLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger('django.request')

    def __call__(self, request):
        self.logger.info(f"{request.method} {request.get_full_path()}")
        return self.get_response(request)

