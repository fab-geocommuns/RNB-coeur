from rest_framework_tracking.mixins import LoggingMixin
from rest_framework_tracking.models import APIRequestLog


class RNBLoggingMixin(LoggingMixin):

    sensitive_fields = {"confirm_password"}  # type: ignore[assignment]

    def should_log(self, request, response):
        return request.query_params.get("from") != "monitoring"

    def handle_log(self):
        data = self.log
        # API responses take too much DB space and are not useful
        data["response"] = None
        APIRequestLog(**data).save()
