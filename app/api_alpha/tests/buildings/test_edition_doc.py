"""
Tests checking that the documentation of the endpoints editing the RNB matches their
serializers: they fail when a field or a rule changes and the doc is not updated.
"""

import json
import re

from api_alpha.serializers.serializers import (
    BuildingCreateSerializer,
    BuildingCreateSerializerCore,
    BuildingMergeSerializer,
    BuildingSplitSerializer,
    BuildingUpdateSerializer,
)
from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from django.test import SimpleTestCase

# (documented path, method) -> serializer validating the request body
EDITION_ENDPOINTS = {
    ("/api/alpha/buildings/", "post"): BuildingCreateSerializer,
    ("/api/alpha/buildings/{rnb_id}/", "patch"): BuildingUpdateSerializer,
    ("/api/alpha/buildings/merge/", "post"): BuildingMergeSerializer,
    ("/api/alpha/buildings/{rnb_id}/split/", "post"): BuildingSplitSerializer,
}


def _body_schema(path: str, method: str) -> dict:
    operation = build_schema_all_endpoints()["paths"][path][method]
    return operation["requestBody"]["content"]["application/json"]["schema"]


def _example_body(schema: dict) -> dict:
    """Build a request body from the examples of the documented properties."""
    body = {}
    for name, prop in schema["properties"].items():
        if "example" in prop:
            body[name] = prop["example"]
        elif prop.get("type") == "array" and "properties" in prop.get("items", {}):
            # a list of objects: two items built from the item examples
            item = _example_body(prop["items"])
            body[name] = [item, item]
    return body


class EditionDocMatchesSerializersTest(SimpleTestCase):
    def test_documented_fields_are_the_serializer_fields(self):
        """
        Input: the request body of each documented editing endpoint.
        Expected: it declares exactly the fields of the serializer, and its required
        fields are the serializer required fields.
        """
        for (path, method), serializer_class in EDITION_ENDPOINTS.items():
            with self.subTest(path=path, method=method):
                schema = _body_schema(path, method)
                fields = serializer_class().get_fields()

                self.assertEqual(set(schema["properties"]), set(fields))
                self.assertEqual(
                    set(schema.get("required", [])),
                    {name for name, field in fields.items() if field.required},
                )

    def test_split_documented_items_are_the_serializer_fields(self):
        """
        Input: the documented items of created_buildings in the split endpoint.
        Expected: they declare exactly the fields of the item serializer, with the
        same required fields.
        """
        items = _body_schema("/api/alpha/buildings/{rnb_id}/split/", "post")[
            "properties"
        ]["created_buildings"]["items"]
        fields = BuildingCreateSerializerCore().get_fields()

        self.assertEqual(set(items["properties"]), set(fields))
        self.assertEqual(
            set(items["required"]),
            {name for name, field in fields.items() if field.required},
        )

    def test_documented_property_examples_are_accepted(self):
        """
        Input: a request body built from the examples of the documented properties of
        each editing endpoint.
        Expected: the serializer of the endpoint accepts it.
        """
        for (path, method), serializer_class in EDITION_ENDPOINTS.items():
            with self.subTest(path=path, method=method):
                body = _example_body(_body_schema(path, method))
                serializer = serializer_class(data=body)
                self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_patch_description_examples_are_valid(self):
        """
        Input: the JSON examples written in the description of PATCH /buildings/{rnb_id}/.
        Expected: each one is valid JSON, uses only documented fields and is accepted
        by the PATCH serializer.
        """
        path, method = "/api/alpha/buildings/{rnb_id}/", "patch"
        description = build_schema_all_endpoints()["paths"][path][method]["description"]
        documented_fields = set(_body_schema(path, method)["properties"])

        examples = re.findall(r"```(\{.*?\})```", description)
        self.assertTrue(examples)

        for example in examples:
            with self.subTest(example=example):
                body = json.loads(example)
                self.assertLessEqual(set(body), documented_fields)
                serializer = BuildingUpdateSerializer(data=body)
                self.assertTrue(serializer.is_valid(), serializer.errors)
