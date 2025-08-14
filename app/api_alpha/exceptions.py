from rest_framework.exceptions import APIException


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = "Service temporarily unavailable, try again later."  # type: ignore[assignment]
    default_code = "service_unavailable"


class BadRequest(APIException):
    status_code = 400
    default_detail = "Bad request."  # type: ignore[assignment]
    default_code = "bad_request"
