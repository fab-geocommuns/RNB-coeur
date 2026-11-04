"""
Tests checking that the published OpenAPI schema matches what the API really does.

The schema is written by hand in the @rnb_doc decorators: these tests fail when the
code changes and the documentation is not updated accordingly.
"""

import json
import re

from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from batid.models import Address, Building, Organization, Plot, UserProfile
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from openapi_schema_validator import OAS31Validator, validate
from rest_framework.test import APITestCase

READ_ONLY_METHODS = ("get", "head", "options")

POLYGON = GEOSGeometry(
    "POLYGON((1.0654705955877262 46.63423852982024, 1.065454930919401 46.634105152847496, "
    "1.0656648374661017 46.63409009413692, 1.0656773692001593 46.63422131990677, "
    "1.0654705955877262 46.63423852982024))",
    srid=4326,
)


def _fill_path_params(path: str) -> str:
    """Replace every {param} of a documented path by a dummy value."""
    return re.sub(r"\{[^}]+\}", "AAAABBBBCCCC", path)


def _resolve(schema: dict, root: dict) -> dict:
    """Follow a local $ref ("#/components/schemas/X") to the schema it points to."""
    while "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        schema = node
    return schema


def _undocumented_keys(instance, schema: dict, root: dict, location: str) -> list[str]:
    """
    List the keys of instance (recursively) that the schema does not declare.

    The schemas have no "additionalProperties: false", so the validator alone does
    not detect a field returned by the API but missing from the documentation.
    """
    schema = _resolve(schema, root)

    # Combinations: a key is documented if one of the sub-schemas declares it
    for keyword in ("allOf", "oneOf", "anyOf"):
        if keyword in schema:
            sub_schemas = [_resolve(s, root) for s in schema[keyword]]
            if keyword != "allOf":
                # keep the sub-schemas that describe the instance
                sub_schemas = [
                    s
                    for s in sub_schemas
                    if OAS31Validator({**s, "components": root["components"]}).is_valid(
                        instance
                    )
                ]
            merged_properties: dict = {}
            for sub_schema in sub_schemas:
                merged_properties.update(sub_schema.get("properties", {}))
            if merged_properties:
                schema = {"type": "object", "properties": merged_properties}
            elif sub_schemas:
                schema = sub_schemas[0]

    missing = []
    if isinstance(instance, dict) and "properties" in schema:
        for key, value in instance.items():
            if key not in schema["properties"]:
                missing.append(f"{location}.{key}")
            else:
                missing += _undocumented_keys(
                    value, schema["properties"][key], root, f"{location}.{key}"
                )
    elif isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            missing += _undocumented_keys(
                item, schema["items"], root, f"{location}[{index}]"
            )
    return missing


class SchemaMatchesAPITest(APITestCase):
    def setUp(self):
        self.schema = build_schema_all_endpoints()

        # a validator belonging to an organization with no short name
        # and a validator belonging to no organization at all
        org = Organization.objects.create(name="Mairie de Dreux")
        with_org = User.objects.create_user(
            username="with_org", email="with_org@test.com"
        )
        UserProfile.objects.create(user=with_org, organization=org)
        without_org = User.objects.create_user(
            username="without_org", email="without_org@test.com"
        )
        UserProfile.objects.create(user=without_org)

        # an address with no city information
        address = Address.objects.create(
            cle_interop="02191_0020_00003",
            source="bdnb",
            street_number=None,
            street_rep=None,
            street=None,
            city_name=None,
            city_zipcode=None,
            city_insee_code=None,
        )

        # A building with every optional field filled, intersecting a plot
        Building.objects.create(
            rnb_id="FULLFULLFULL",
            shape=POLYGON,
            point=POLYGON.point_on_surface,
            status="constructed",
            addresses_internal_id=[address.internal_id],
            ext_ids=[
                {
                    "source": "bdnb",
                    "id": "bdnb-bc-3B85-TYM9-FDSX",
                    "created_at": "2025-12-25T00:00:00.000000+00:00",
                    "source_version": None,
                }
            ],
            validated_by=[with_org.id, without_org.id],
        )
        Plot.objects.create(id="01402000AB0051", shape=MultiPolygon(POLYGON, srid=4326))

        # A building with a point as shape, no ext_ids and no plot around it
        point = GEOSGeometry("POINT(2.35 48.85)", srid=4326)
        Building.objects.create(
            rnb_id="POINTPOINTPO",
            shape=point,
            point=point,
            status="demolished",
            ext_ids=None,
        )

        # A building without any shape
        Building.objects.create(
            rnb_id="NOSHAPENOSHA",
            shape=None,
            point=point,
            status="notUsable",
            is_active=False,
        )

    def _operations(self):
        for path, path_item in self.schema["paths"].items():
            for method, operation in path_item.items():
                yield path, method, operation

    def _response_schema(self, path: str, method: str, code: str) -> dict:
        response = self.schema["paths"][path][method]["responses"][code]
        return response["content"]["application/json"]["schema"]

    def _assert_matches_schema(self, instance, schema: dict, location: str) -> None:
        root = {"components": self.schema["components"]}
        validate(instance, {**schema, **root}, cls=OAS31Validator)
        self.assertEqual(
            _undocumented_keys(instance, schema, root, location),
            [],
            "Fields returned by the API but missing from the documentation",
        )

    def test_write_operations_document_the_token(self):
        """
        Input: every documented operation that is not a read (POST, PATCH...).
        Expected: it declares the tokenAuth security scheme and a 401 response, and the
        API really answers 401 when it is called without a token.
        """
        self.assertIn("tokenAuth", self.schema["components"]["securitySchemes"])

        write_operations = [
            (path, method, operation)
            for path, method, operation in self._operations()
            if method not in READ_ONLY_METHODS
        ]
        self.assertTrue(write_operations)

        for path, method, operation in write_operations:
            with self.subTest(path=path, method=method):
                self.assertIn({"tokenAuth": []}, operation.get("security", []))
                self.assertIn("401", operation["responses"])

                r = getattr(self.client, method)(
                    _fill_path_params(path), {}, format="json"
                )
                self.assertEqual(r.status_code, 401)

    def test_read_operations_need_no_token(self):
        """
        Input: every documented read operation (GET).
        Expected: it declares no security requirement, and the API never answers 401
        or 403 to an anonymous call. It documents a 401, which the API returns when
        an invalid token is sent.
        """
        for path, method, operation in self._operations():
            if method not in READ_ONLY_METHODS:
                continue
            with self.subTest(path=path, method=method):
                self.assertNotIn("security", operation)
                r = self.client.get(_fill_path_params(path))
                self.assertNotIn(r.status_code, (401, 403))

                self.assertIn("401", operation["responses"])
                r = self.client.get(
                    _fill_path_params(path), HTTP_AUTHORIZATION="Token invalide"
                )
                self.assertEqual(r.status_code, 401)

    def test_every_operation_has_a_tag(self):
        """
        Input: every documented operation.
        Expected: it is tagged OGC, Bâtiments (reads) or Édition (writes).
        """
        for path, method, operation in self._operations():
            with self.subTest(path=path, method=method):
                self.assertIn(
                    operation.get("tags"), (["OGC"], ["Bâtiments"], ["Édition"])
                )

    def test_operations_without_400_never_answer_400(self):
        """
        Input: every documented GET operation that does not list a 400 response,
        called with unexpected query parameters.
        Expected: the API does not answer 400.
        """
        for path, method, operation in self._operations():
            if method != "get" or "400" in operation["responses"]:
                continue
            with self.subTest(path=path):
                r = self.client.get(
                    _fill_path_params(path),
                    {"format": "unknown", "withPlots": "abc", "limit": "-1"},
                )
                self.assertNotEqual(r.status_code, 400)

    def test_single_building_matches_documented_response(self):
        """
        Input: GET /buildings/{rnb_id}/?withPlots=1 on a complete building, a building
        with a point shape and no plot, and a building with no shape.
        Expected: each response validates against the documented 200 schema (null
        values included) and returns no field missing from the documentation.
        """
        schema = self._response_schema("/api/alpha/buildings/{rnb_id}/", "get", "200")

        for rnb_id in ("FULLFULLFULL", "POINTPOINTPO", "NOSHAPENOSHA"):
            with self.subTest(rnb_id=rnb_id):
                r = self.client.get(f"/api/alpha/buildings/{rnb_id}/?withPlots=1")
                self.assertEqual(r.status_code, 200)
                self._assert_matches_schema(json.loads(r.content), schema, rnb_id)

    def test_ogc_item_matches_documented_response(self):
        """
        Input: GET on the OGC item of the complete building, of the building with
        a point shape and of the building without shape, with withPlots=1.
        Expected: each response validates against the documented BuildingGeoJSON
        schema and returns no field missing from the documentation.
        """
        schema = {"$ref": "#/components/schemas/BuildingGeoJSON"}

        for rnb_id in ("FULLFULLFULL", "POINTPOINTPO", "NOSHAPENOSHA"):
            with self.subTest(rnb_id=rnb_id):
                r = self.client.get(
                    f"/api/alpha/ogc/collections/buildings/items/{rnb_id}?withPlots=1"
                )
                self.assertEqual(r.status_code, 200)
                self._assert_matches_schema(json.loads(r.content), schema, rnb_id)
