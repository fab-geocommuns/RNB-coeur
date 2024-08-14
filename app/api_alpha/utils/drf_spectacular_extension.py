from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from rest_framework import serializers

from batid.utils.misc import root_url_from_request

excluded_endpoints = [
    "/api/alpha/login/",
    "/api/alpha/schema/",
]


def request_for_spectacular_middleware(get_response):
    def middleware(request):

        if request.path == "/api/alpha/schema/":

            global root_url
            root_url = root_url_from_request(request)

        response = get_response(request)
        return response

    return middleware


def filter_endpoints_hook(endpoints):
    return [endpoint for endpoint in endpoints if endpoint[0] not in excluded_endpoints]


# This DRF Spectacular extension move the help_text from a serialized field
# from the "description" property to the "example" property
class AddExampleToOpenAPIFields(OpenApiSerializerFieldExtension):
    target_class = serializers.Field
    match_subclasses = True

    def map_serializer_field(self, auto_schema, direction):
        default = auto_schema._map_serializer_field(
            self.target, direction, bypass_extensions=True
        )

        if self.target.help_text is not None:
            default["example"] = self.target.help_text

        return default


def host_prefixed_paths(endpoints):

    new_endpoints = []

    for path, path_regex, method, callback in endpoints:
        new_endpoints.append((f"{root_url}{path}", path_regex, method, callback))

    print(new_endpoints)

    return new_endpoints
