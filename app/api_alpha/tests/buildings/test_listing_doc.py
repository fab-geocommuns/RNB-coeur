"""
Tests checking that the documentation of the building listing and lookup matches
what these endpoints really do.
"""

import re

from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from batid.models import Address, Building
from batid.services.bdg_status import BuildingStatus
from django.contrib.gis.geos import GEOSGeometry
from openapi_schema_validator import OAS31Validator, validate
from rest_framework.test import APITestCase

LIST_PATH = "/api/alpha/buildings/"
SINGLE_PATH = "/api/alpha/buildings/{rnb_id}/"

POLYGON = GEOSGeometry(
    "POLYGON((2.4290 48.8420, 2.4300 48.8420, 2.4300 48.8430, "
    "2.4290 48.8430, 2.4290 48.8420))",
    srid=4326,
)


class ListingDocTest(APITestCase):
    def setUp(self):
        self.schema = build_schema_all_endpoints()
        self.list_doc = self.schema["paths"][LIST_PATH]["get"]
        self.params = {p["name"]: p for p in self.list_doc["parameters"]}

        # a building inside the documented bbox and bb examples, with the
        # documented cle_interop_ban example as address
        address = Address.objects.create(
            cle_interop=self.params["cle_interop_ban"]["example"],
            source="ban",
            # null city fields are documented by the schema fixes of #1125
            street_number="73",
            street_rep="",
            street="rue de Paris",
            city_name="Saint-Mandé",
            city_zipcode="94160",
            city_insee_code="94067",
        )
        Building.objects.create(
            rnb_id="DOCEXAMPLE01",
            shape=POLYGON,
            point=POLYGON.point_on_surface,
            status="constructed",
            addresses_internal_id=[address.internal_id],
            # null ext_ids are documented by the schema fixes of #1125
            ext_ids=[
                {
                    "source": "bdnb",
                    "id": "bdnb-bc-3B85-TYM9-FDSX",
                    "created_at": "2025-12-25T00:00:00.000000+00:00",
                    "source_version": None,
                }
            ],
        )

    def _validate(self, instance, schema: dict) -> None:
        validate(
            instance,
            {**schema, "components": self.schema["components"]},
            cls=OAS31Validator,
        )

    def test_documented_filters_are_the_required_ones(self):
        """
        Input: each documented listing parameter, sent alone with its example value.
        Expected: the parameters the description lists as filters are accepted alone
        (no 400), every other parameter is refused alone (400).
        """
        line = next(
            line
            for line in self.list_doc["description"].splitlines()
            if line.startswith("Au moins un de ces filtres est requis")
        )
        documented_filters = set(re.findall(r"`(\w+)`", line))
        self.assertTrue(documented_filters)

        for name, param in self.params.items():
            with self.subTest(param=name):
                r = self.client.get(LIST_PATH, {name: param["example"]})
                if name in documented_filters:
                    self.assertNotEqual(r.status_code, 400, r.content)
                else:
                    self.assertEqual(r.status_code, 400)

    def test_status_doc_lists_every_status_and_default(self):
        """
        Input: the documentation of the status parameter.
        Expected: it names every BuildingStatus key, the "all" value and the
        statuses listed by default.
        """
        description = self.params["status"]["description"]
        for status in BuildingStatus.ALL_TYPES_KEYS:
            self.assertIn(f"<b>{status}</b>", description)
        self.assertIn("`all`", description)
        self.assertIn(", ".join(BuildingStatus.REAL_BUILDINGS_STATUS), description)

    def _validate_response(self, r, operation_doc: dict) -> None:
        """Validate a response against the schema documented for its real
        status code and Content-Type."""
        media_type = r["Content-Type"].split(";")[0]
        content = operation_doc["responses"][str(r.status_code)]["content"]
        self.assertIn(media_type, content)
        self._validate(r.json(), content[media_type]["schema"])

    def test_examples_return_documented_responses(self):
        """
        Input: the documented bbox and bb examples, in json then geojson format.
        Expected: 200 with the example building, and each response validates against
        the schema documented for its real Content-Type (one oneOf branch only).
        """
        for filter_name in ("bbox", "bb"):
            for fmt in ("json", "geojson"):
                with self.subTest(filter=filter_name, format=fmt):
                    r = self.client.get(
                        LIST_PATH,
                        {
                            filter_name: self.params[filter_name]["example"],
                            "format": fmt,
                        },
                    )
                    self.assertEqual(r.status_code, 200)
                    data = r.json()
                    items = data["results"] if fmt == "json" else data["features"]
                    self.assertEqual(len(items), 1)
                    self._validate_response(r, self.list_doc)

    def test_listing_404_is_documented(self):
        """
        Input: listing on an INSEE code matching no city.
        Expected: the API answers 404 and the documentation lists a 404 response.
        """
        r = self.client.get(LIST_PATH, {"insee_code": "99999"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("404", self.list_doc["responses"])

    def test_lookup_matches_documentation(self):
        """
        Input: lookup of an existing building in json then geojson format, then of
        an unknown RNB ID.
        Expected: each 200 response validates against the schema documented for its
        real Content-Type, and the unknown RNB ID gives the documented 404.
        """
        single_doc = self.schema["paths"][SINGLE_PATH]["get"]

        for fmt in ("json", "geojson"):
            with self.subTest(format=fmt):
                r = self.client.get(
                    "/api/alpha/buildings/DOCEXAMPLE01/", {"format": fmt}
                )
                self.assertEqual(r.status_code, 200)
                self._validate_response(r, single_doc)

        r = self.client.get("/api/alpha/buildings/UNKNOWNRNBID/")
        self.assertEqual(r.status_code, 404)
        self.assertIn("404", single_doc["responses"])
