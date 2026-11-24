"""
Tests checking that the documentation of the building listing and lookup matches
what these endpoints really do.
"""

import re

from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from batid.models import Address, Building, City
from batid.services.bdg_status import BuildingStatus
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from openapi_schema_validator import OAS31Validator, validate
from rest_framework.test import APITestCase

LIST_PATH = "/api/alpha/buildings/"
SINGLE_PATH = "/api/alpha/buildings/{rnb_id}/"

POLYGON = GEOSGeometry(
    "POLYGON((2.4290 48.8420, 2.4300 48.8420, 2.4300 48.8430, "
    "2.4290 48.8430, 2.4290 48.8420))",
    srid=4326,
)

# Shape crossing the east edge of the documented bbox, its point being outside
EDGE_POLYGON = GEOSGeometry(
    "POLYGON((2.4330 48.8420, 2.4450 48.8420, 2.4450 48.8430, "
    "2.4330 48.8430, 2.4330 48.8420))",
    srid=4326,
)
EDGE_POINT = GEOSGeometry("POINT(2.4440 48.8425)", srid=4326)


class ListingDocTest(APITestCase):
    def setUp(self):
        self.schema = build_schema_all_endpoints()
        self.list_doc = self.schema["paths"][LIST_PATH]["get"]
        self.params = {p["name"]: p for p in self.list_doc["parameters"]}

        # the city of the documented insee_code example, covering the documented
        # bbox example (the bb example is the same box)
        min_lon, min_lat, max_lon, max_lat = map(
            float, self.params["bbox"]["example"].split(",")
        )
        City.objects.create(
            code_insee=self.params["insee_code"]["example"],
            name="Saint-Mandé",
            shape=MultiPolygon(
                Polygon.from_bbox((min_lon, min_lat, max_lon, max_lat)), srid=4326
            ),
        )

        # a building inside the documented bbox and bb examples, with the
        # documented cle_interop_ban and ban_id examples as address
        address = Address.objects.create(
            cle_interop=self.params["cle_interop_ban"]["example"],
            ban_id=self.params["ban_id"]["example"],
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

        # never listed with the documented filter examples: an inactive building
        # inside the area, and a building whose shape enters the area while its
        # point stays outside
        Building.objects.create(
            rnb_id="INACTIVE0001",
            shape=POLYGON,
            point=POLYGON.point_on_surface,
            status="constructed",
            is_active=False,
            addresses_internal_id=[address.internal_id],
        )
        Building.objects.create(
            rnb_id="EDGEPOINT001",
            shape=EDGE_POLYGON,
            point=EDGE_POINT,
            status="constructed",
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
        Expected: each parameter the description lists as a filter is accepted alone
        and returns the example building only (not the inactive building, nor the
        building whose point is outside the area); every other parameter is refused
        alone (400).
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
                    self.assertEqual(r.status_code, 200, r.content)
                    self.assertEqual(
                        {b["rnb_id"] for b in r.json()["results"]}, {"DOCEXAMPLE01"}
                    )
                else:
                    self.assertEqual(r.status_code, 400)

    def test_documented_status_example_is_accepted(self):
        """
        Input: listing with the documented status example and the bbox example.
        Expected: 200.
        """
        r = self.client.get(
            LIST_PATH,
            {
                "status": self.params["status"]["example"],
                "bbox": self.params["bbox"]["example"],
            },
        )
        self.assertEqual(r.status_code, 200, r.content)

    def test_insee_code_example_is_a_commune(self):
        """
        Input: the documented insee_code example.
        Expected: a commune code, not the code of an arrondissement of Paris, Lyon or
        Marseille: the cities table only holds communes, so such a code answers 404.
        """
        example = self.params["insee_code"]["example"]
        self.assertRegex(example, r"^\d[\dAB]\d{3}$")
        self.assertIsNone(
            re.match(r"^(751(0[1-9]|1\d|20)|6938[1-9]|132(0[1-9]|1[0-6]))$", example),
            f"{example} is an arrondissement code",
        )

    def test_doc_states_which_buildings_are_listed(self):
        """
        Input: the documentation of the listing and of its geographic filters.
        Expected: it states that only active buildings are listed and that the
        geographic filters work on the point of the building (the behaviour is
        checked by test_documented_filters_are_the_required_ones).
        """
        description = self.list_doc["description"]
        self.assertIn("seuls les bâtiments actifs sont listés", description)
        self.assertIn(
            "Les filtres géographiques (`bbox`, `bb`, `insee_code`) portent sur le "
            "point du bâtiment",
            description,
        )
        for name in ("bbox", "bb", "insee_code"):
            with self.subTest(param=name):
                param_description = self.params[name]["description"]
                self.assertIn("point (localisation)", param_description)
                self.assertNotIn("emprise", param_description)

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
        Expected: the API answers 404, and the documentation lists a 404 response
        and states it in the insee_code parameter.
        """
        r = self.client.get(LIST_PATH, {"insee_code": "99999"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("404", self.list_doc["responses"])
        self.assertIn(
            "code INSEE inconnu renvoie une erreur 404",
            self.params["insee_code"]["description"],
        )

    def test_insee_code_of_wrong_length_is_400(self):
        """
        Input: listing on INSEE codes of 4 and 6 characters.
        Expected: 400 (not the 404 of an unknown code), as the insee_code
        documentation states.
        """
        self.assertIn(
            "Le code doit faire 5 caractères, sinon la requête est refusée (erreur 400)",
            self.params["insee_code"]["description"],
        )
        for code in ("9406", "940670"):
            with self.subTest(insee_code=code):
                r = self.client.get(LIST_PATH, {"insee_code": code})
                self.assertEqual(r.status_code, 400)

    def test_invalid_cursor_is_documented_404(self):
        """
        Input: the bbox example with an invalid pagination cursor, in json then
        geojson format.
        Expected: 404, and the documented 404 response mentions the cursor.
        """
        self.assertIn("cursor", self.list_doc["responses"]["404"]["description"])
        for fmt in ("json", "geojson"):
            with self.subTest(format=fmt):
                r = self.client.get(
                    LIST_PATH,
                    {
                        "bbox": self.params["bbox"]["example"],
                        "cursor": "zzz",
                        "format": fmt,
                    },
                )
                self.assertEqual(r.status_code, 404)

    def test_empty_status_returns_no_building(self):
        """
        Input: the bbox example with an empty status ("status=").
        Expected: 200 with no building (neither the default statuses nor a 400), as
        the status documentation states.
        """
        self.assertIn(
            "Une valeur vide (`status=`) ne renvoie aucun bâtiment",
            self.params["status"]["description"],
        )
        r = self.client.get(
            LIST_PATH, {"bbox": self.params["bbox"]["example"], "status": ""}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["results"], [])

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
