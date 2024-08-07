from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from rest_framework import serializers

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
            default.pop("description", None)

        return default
