from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import APIException


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = _("Service temporarily unavailable, try again later.")
    default_code = "service_unavailable"


class BadRequest(APIException):
    status_code = 400
    default_detail = _("Bad request.")
    default_code = "bad_request"


class TooManyContributions(APIException):
    status_code = 403
    default_detail = _("Maximum number of contributions reached.")
    default_code = "too_many_contributions"
