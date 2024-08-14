from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from rest_framework import serializers

from batid.utils.misc import root_url_from_request

excluded_endpoints = [
    "/api/alpha/login/",
    "/api/alpha/schema/",
]


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


def full_url_paths(result, generator, request, public):

    root = root_url_from_request(request)

    new_paths = {}

    for path in result["paths"]:

        full_url = f"{root}{path}"
        new_paths[full_url] = result["paths"][path]

    result["paths"] = new_paths

    return result
