"""
Tests checking that the documentation of the search endpoints (closest, address,
intersect, plot, change_stats) matches what they really do.
"""

from unittest.mock import patch

from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from batid.exceptions import BANAPIDown
from batid.models import Building, Plot
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from openapi_schema_validator import OAS31Validator, validate
from rest_framework.test import APITestCase

# Two buildings a few meters away from the documented closest example point
CLOSEST_POINT = (44.8201164915397, -0.5717449803671368)
POLYGONS = [
    GEOSGeometry(
        f"POLYGON(({lng} {lat}, {lng + 0.0001} {lat}, {lng + 0.0001} {lat + 0.0001}, "
        f"{lng} {lat + 0.0001}, {lng} {lat}))",
        srid=4326,
    )
    for lat, lng in (
        (CLOSEST_POINT[0], CLOSEST_POINT[1]),
        (CLOSEST_POINT[0] + 0.0003, CLOSEST_POINT[1]),
    )
]

PAGINATED_OPERATIONS = (
    "closestBuildings",
    "address",
    "intersectBuildings",
    "plotBuildings",
)


class SearchDocTest(APITestCase):
    def setUp(self):
        self.schema = build_schema_all_endpoints()

        for index, polygon in enumerate(POLYGONS):
            Building.objects.create(
                rnb_id=f"CLOSEST{index:05d}",
                shape=polygon,
                point=polygon.point_on_surface,
                status="constructed",
                ext_ids=[],
            )
        Plot.objects.create(
            id="PLOTWITHBDGS",
            shape=MultiPolygon(POLYGONS[0].buffer(0.001), srid=4326),
        )

    def _operation(self, operation_id: str) -> tuple[str, dict]:
        """Return the path and the documentation of the operation with this id."""
        for path, path_item in self.schema["paths"].items():
            for operation in path_item.values():
                if operation.get("operationId") == operation_id:
                    return path, operation
        raise AssertionError(f"{operation_id} is not documented")

    def _params(self, operation_id: str) -> dict:
        _, operation = self._operation(operation_id)
        return {p["name"]: p for p in operation.get("parameters", [])}

    def _resolve(self, schema: dict) -> dict:
        """Follow a local $ref, possibly pointing inside a component."""
        while "$ref" in schema:
            node: dict = self.schema
            for part in schema["$ref"].lstrip("#/").split("/"):
                node = node[part]
            schema = node
        return schema

    def _validate(self, instance, schema: dict) -> None:
        validate(
            instance,
            {**schema, "components": self.schema["components"]},
            cls=OAS31Validator,
        )

    def _get(self, url: str, params: dict | None = None):
        return self.client.get(url, params or {})

    # ---------- pagination

    def test_paginated_operations_document_limit_and_cursor(self):
        """
        Input: closest with the documented limit set to 1, then the next page.
        Expected: every paginated search operation documents limit and cursor; limit
        is applied, the "next" URL gives the second building, and a limit out of the
        documented range gives a 400.
        """
        for operation_id in PAGINATED_OPERATIONS:
            with self.subTest(operation=operation_id):
                self.assertIn("limit", self._params(operation_id))
                self.assertIn("cursor", self._params(operation_id))

        limit = self._params("closestBuildings")["limit"]["schema"]
        point = f"{CLOSEST_POINT[0]},{CLOSEST_POINT[1]}"

        r = self._get(
            "/api/alpha/buildings/closest/",
            {"point": point, "radius": 100, "limit": 1},
        )
        self.assertEqual(r.status_code, 200)
        first_page = r.json()
        self.assertEqual(len(first_page["results"]), 1)

        r = self.client.get(first_page["next"])
        self.assertEqual(r.status_code, 200)
        second_page = r.json()["results"]
        self.assertEqual(len(second_page), 1)
        self.assertNotEqual(
            second_page[0]["rnb_id"], first_page["results"][0]["rnb_id"]
        )

        for out_of_range in (limit["minimum"] - 1, limit["maximum"] + 1):
            r = self._get(
                "/api/alpha/buildings/closest/",
                {"point": point, "radius": 100, "limit": out_of_range},
            )
            self.assertEqual(r.status_code, 400)

    # ---------- closest

    def test_closest_documents_exactly_the_returned_fields(self):
        """
        Input: closest around the documented example point.
        Expected: the response validates against the documented schema, and each
        result has exactly the documented fields (no more, no less).
        """
        path, operation = self._operation("closestBuildings")
        response_schema = operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        documented_fields: set[str] = set()
        for sub_schema in response_schema["properties"]["results"]["items"]["allOf"]:
            documented_fields |= set(self._resolve(sub_schema)["properties"])

        r = self._get(
            path,
            {
                "point": self._params("closestBuildings")["point"]["example"],
                "radius": 100,
            },
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["results"])
        self._validate(data, response_schema)
        for result in data["results"]:
            self.assertEqual(set(result), documented_fields)

    # ---------- address

    def test_address_parameter_rules(self):
        """
        Input: address with both q and cle_interop_ban, with none of them, and with
        min_score next to cle_interop_ban.
        Expected: 400 each time, as the documentation says.
        """
        params = self._params("address")
        q = params["q"]["example"]
        cle = params["cle_interop_ban"]["example"]

        for query in (
            {"q": q, "cle_interop_ban": cle},
            {},
            {"cle_interop_ban": cle, "min_score": 0.5},
        ):
            with self.subTest(query=query):
                r = self._get("/api/alpha/buildings/address/", query)
                self.assertEqual(r.status_code, 400)

    @patch(
        "api_alpha.views.BanGeocoder.cle_interop_ban_best_result",
        side_effect=BANAPIDown,
    )
    def test_address_503_is_documented(self, _mock):
        """
        Input: address search with q while the BAN geocoder is down.
        Expected: the API answers 503 and the documentation lists a 503 response.
        """
        r = self._get(
            "/api/alpha/buildings/address/",
            {"q": self._params("address")["q"]["example"]},
        )
        self.assertEqual(r.status_code, 503)
        _, operation = self._operation("address")
        self.assertIn("503", operation["responses"])

    # ---------- plot

    def test_plot(self):
        """
        Input: buildings of a known plot, then of an unknown plot.
        Expected: the known plot response validates against the documented schema;
        the unknown plot gives the documented 404.
        """
        _, operation = self._operation("plotBuildings")

        r = self._get("/api/alpha/buildings/plot/PLOTWITHBDGS/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["results"])
        self._validate(
            r.json(),
            operation["responses"]["200"]["content"]["application/json"]["schema"],
        )

        r = self._get("/api/alpha/buildings/plot/UNKNOWNPLOT/")
        self.assertEqual(r.status_code, 404)
        self.assertIn("404", operation["responses"])

    # ---------- change_stats

    def test_change_stats_matches_documented_response(self):
        """
        Input: change_stats with the documented since and until examples.
        Expected: 200, one entry per day, validating against the documented schema.
        """
        path, operation = self._operation("getBuildingChangeStats")
        params = self._params("getBuildingChangeStats")

        r = self._get(
            path,
            {"since": params["since"]["example"], "until": params["until"]["example"]},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 31)
        self._validate(
            r.json(),
            operation["responses"]["200"]["content"]["application/json"]["schema"],
        )
