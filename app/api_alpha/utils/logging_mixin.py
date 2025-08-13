from rest_framework_tracking.mixins import LoggingMixin


class RNBLoggingMixin(LoggingMixin):

    sensitive_fields = {"confirm_password"} # type: ignore[assignment]

    def should_log(self, request, response):
        return request.query_params.get("from") != "monitoring"
