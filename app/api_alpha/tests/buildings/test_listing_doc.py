"""
Tests checking that the documentation of the building listing and lookup matches
what these endpoints really do.
"""

import re

from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from batid.models import Address, Building, City
from batid.services.bdg_status import BuildingStatus
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from jsonschema.exceptions import ValidationError
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

# Statuses the lookup serves, as written in the documentation:
# `constructed`, `notUsable` ou `demolished`
ALL_STATUS_MD = (
    ", ".join(f"`{s}`" for s in BuildingStatus.ALL_TYPES_KEYS[:-1])
    + f" ou `{BuildingStatus.ALL_TYPES_KEYS[-1]}`"
)


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
        statuses listed by default, without calling them "réels": the OGC and
        GitBook documentation give that word other meanings (active, or active with
        these statuses).
        """
        description = self.params["status"]["description"]
        for status in BuildingStatus.ALL_TYPES_KEYS:
            self.assertIn(f"<b>{status}</b>", description)
        self.assertIn("`all`", description)
        self.assertIn(", ".join(BuildingStatus.REAL_BUILDINGS_STATUS), description)
        self.assertNotIn("réels", description)
        self.assertNotIn("réels", self.list_doc["description"])

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
                    if fmt == "geojson":
                        # the documented timeStamp example has the real shape
                        # (milliseconds and Z)
                        shape = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$"
                        example = self.list_doc["responses"]["200"]["content"][
                            "application/json"
                        ]["schema"]["oneOf"][1]["properties"]["timeStamp"]["example"]
                        self.assertRegex(data["timeStamp"], shape)
                        self.assertRegex(example, shape)

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
            "un code entouré d'espaces compris, voir `insee_code`",
            self.list_doc["responses"]["404"]["description"],
        )
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
        description = self.params["insee_code"]["description"]
        self.assertIn(
            "Le code doit faire 5 caractères, sans espace : un code plus court ou "
            "plus long est refusé (erreur 400)",
            description,
        )
        self.assertNotIn("un code d'une autre longueur est refusé", description)
        for code in ("9406", "940670", "9406 "):
            with self.subTest(insee_code=code):
                r = self.client.get(LIST_PATH, {"insee_code": code})
                self.assertEqual(r.status_code, 400)

    def test_insee_code_with_spaces_does_not_list(self):
        """
        Input: the documented insee_code example with a space before, then after.
        Expected: 404 although the code has 6 characters (the spaces are not counted
        in the length, but the view looks up the raw value, spaces included), as the
        insee_code documentation states.
        """
        # Documents a defect: the view looks up the raw value instead of the
        # validated one. Fixing #1276 changes this 404 and the documentation.
        self.assertIn(
            "Une espace avant ou après le code n'est pas comptée dans la longueur, "
            "mais fait échouer la recherche (erreur 404)",
            self.params["insee_code"]["description"],
        )
        example = self.params["insee_code"]["example"]
        for code in (" " + example, example + " "):
            with self.subTest(insee_code=code):
                r = self.client.get(LIST_PATH, {"insee_code": code})
                self.assertEqual(r.status_code, 404)

    def test_arrondissement_code_is_documented_404(self):
        """
        Input: listing on the INSEE codes of an arrondissement of Paris and of Lyon.
        Expected: 404 (the cities table only holds communes), as the insee_code
        documentation states.
        """
        description = self.params["insee_code"]["description"]
        self.assertIn("arrondissement", description)
        for code in ("75101", "69381"):
            with self.subTest(insee_code=code):
                self.assertIn(code, description)
                r = self.client.get(LIST_PATH, {"insee_code": code})
                self.assertEqual(r.status_code, 404)

    def test_bbox_area_limit_is_documented(self):
        """
        Input: bbox of an area of exactly 4 square degrees, then just above 4.
        Expected: 200 at 4, 400 above, and the bbox description states that the area
        must not exceed 4 (about 34 000 km²), not that it must be below 4.
        """
        description = self.params["bbox"]["description"]
        self.assertIn("ne doit pas dépasser 4", description)
        self.assertIn("34 000 km²", description)
        self.assertNotIn("< 4", description)
        self.assertNotIn("deux départements", description)

        r = self.client.get(LIST_PATH, {"bbox": "2,48,4,50"})
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.get(LIST_PATH, {"bbox": "2,48,4.0001,50"})
        self.assertEqual(r.status_code, 400)

    def test_bb_doc_promises_no_area_limit(self):
        """
        Input: a bb of 410 square degrees, and a valid bb around Brest (negative
        longitudes).
        Expected: the first is accepted and the second refused (bb compares its
        coordinates as text), so the bb description promises no area limit.
        """
        description = self.params["bb"]["description"]
        self.assertNotIn("La taille est limitée", description)
        self.assertNotIn("ne doit pas dépasser", description)
        self.assertNotIn("km²", description)

        r = self.client.get(LIST_PATH, {"bb": "9,-5,50,5"})
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.get(LIST_PATH, {"bb": "48.40,-4.50,48.38,-4.48"})
        self.assertEqual(r.status_code, 400)

    def test_bbox_and_bb_together_is_documented_400(self):
        """
        Input: listing with both the bbox and the bb examples.
        Expected: 400, and each of the two descriptions states it cannot be
        combined with the other.
        """
        r = self.client.get(
            LIST_PATH,
            {
                "bbox": self.params["bbox"]["example"],
                "bb": self.params["bb"]["example"],
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn(
            "Ne peut pas être combiné avec `bb`", self.params["bbox"]["description"]
        )
        self.assertIn(
            "Ne peut pas être combiné avec `bbox`", self.params["bb"]["description"]
        )

    def test_documented_page_links_can_be_followed(self):
        """
        Input: the documented next and previous example URLs, followed as is.
        Expected: 200 (they keep a filter, like the real links), and the cursor
        they carry is a documented parameter.
        """
        self.assertIn("cursor", self.params)
        properties = self.list_doc["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["oneOf"][0]["properties"]
        for link in ("next", "previous"):
            with self.subTest(link=link):
                example = properties[link]["example"]
                url = example[example.index(LIST_PATH) :]
                self.assertIn("cursor=", url)
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200, r.content)

    def test_geojson_listing_type_is_a_constant(self):
        """
        Input: the documented geojson listing schema, and a page whose type is not
        FeatureCollection.
        Expected: the schema fixes type to FeatureCollection, so the page is refused.
        """
        schema = self.list_doc["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["oneOf"][1]
        self.assertEqual(schema["properties"]["type"].get("const"), "FeatureCollection")
        with self.assertRaises(ValidationError):
            self._validate({"type": "Feature", "features": [], "links": []}, schema)

    def test_invalid_cursor_is_documented_404(self):
        """
        Input: the bbox example with an unreadable pagination cursor (not base64),
        in json then geojson format.
        Expected: 404, and the documentation promises the 404 for an unreadable
        cursor only: a readable cursor holding a position that is not an integer
        answers 500 today, so the doc must not promise 404 for any invalid cursor.
        """
        self.assertIn(
            "le curseur de pagination (`cursor`) est illisible",
            self.list_doc["responses"]["404"]["description"],
        )
        cursor_doc = self.params["cursor"]["description"]
        self.assertIn("Un curseur illisible renvoie une erreur 404", cursor_doc)
        self.assertNotIn("Un curseur invalide renvoie une erreur 404", cursor_doc)
        self.assertNotIn(
            "n'est pas valide", self.list_doc["responses"]["404"]["description"]
        )
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
        Input: the bbox example with an empty status ("status="), then with a status
        made of spaces only.
        Expected: 200 with no building for the empty value (neither the default
        statuses nor a 400), 400 for the spaces, as the status documentation states.
        """
        self.assertIn(
            "Une valeur vide (`status=`) ne renvoie aucun bâtiment ; une valeur faite "
            "seulement d'espaces est refusée (erreur 400)",
            self.params["status"]["description"],
        )
        r = self.client.get(
            LIST_PATH, {"bbox": self.params["bbox"]["example"], "status": ""}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["results"], [])

        r = self.client.get(
            LIST_PATH, {"bbox": self.params["bbox"]["example"], "status": " "}
        )
        self.assertEqual(r.status_code, 400)

    def test_lookup_doc_compares_statuses_with_listing_default(self):
        """
        Input: a demolished building in the bbox example, listed without status,
        listed with status=demolished, and looked up.
        Expected: absent from the default listing only; the lookup documentation
        says the listing excludes demolished buildings by default, not always.
        """
        description = self.schema["paths"][SINGLE_PATH]["get"]["description"]
        self.assertIn(
            "et, par défaut, que les statuts "
            + " et ".join(f"`{s}`" for s in BuildingStatus.REAL_BUILDINGS_STATUS),
            description,
        )
        self.assertNotIn("et tous les statuts, démolis compris", description)

        Building.objects.create(
            rnb_id="DEMOLISHED01",
            shape=POLYGON,
            point=POLYGON.point_on_surface,
            status="demolished",
        )
        bbox = self.params["bbox"]["example"]
        r = self.client.get(LIST_PATH, {"bbox": bbox})
        self.assertNotIn("DEMOLISHED01", {b["rnb_id"] for b in r.json()["results"]})
        r = self.client.get(LIST_PATH, {"bbox": bbox, "status": "demolished"})
        self.assertEqual({b["rnb_id"] for b in r.json()["results"]}, {"DEMOLISHED01"})
        r = self.client.get("/api/alpha/buildings/DEMOLISHED01/")
        self.assertEqual(r.status_code, 200)

    def test_lookup_doc_names_the_statuses_it_serves(self):
        """
        Input: lookup of an inactive building of a served status, then of an inactive
        building whose status was retired from the code (2 such buildings exist in
        production, deactivated before the retirement).
        Expected: 200 then 404, so the listing and lookup documentation name the
        served statuses instead of promising every status or every inactive building.
        """
        list_description = self.list_doc["description"]
        lookup_doc = self.schema["paths"][SINGLE_PATH]["get"]
        self.assertIn(
            "Un bâtiment désactivé reste accessible par la consultation d'un "
            f"bâtiment s'il est de statut {ALL_STATUS_MD}",
            list_description,
        )
        self.assertIn(
            f"Il renvoie les bâtiments de statut {ALL_STATUS_MD}, qu'ils soient "
            "actifs ou désactivés",
            lookup_doc["description"],
        )
        self.assertNotIn("tous les statuts", lookup_doc["description"])
        self.assertNotIn(
            "renvoie aussi les bâtiments désactivés", lookup_doc["description"]
        )
        self.assertEqual(
            lookup_doc["responses"]["404"]["description"],
            f"Aucun bâtiment de statut {ALL_STATUS_MD} ne correspond à cet "
            "identifiant RNB.",
        )

        r = self.client.get("/api/alpha/buildings/INACTIVE0001/")
        self.assertEqual(r.status_code, 200)

        Building.objects.create(
            rnb_id="RETIREDSTAT1",
            shape=POLYGON,
            point=POLYGON.point_on_surface,
            status="ongoingChange",
            is_active=False,
        )
        r = self.client.get("/api/alpha/buildings/RETIREDSTAT1/")
        self.assertEqual(r.status_code, 404)

    def test_lookup_matches_documentation(self):
        """
        Input: lookup of an existing building in json then geojson format, then of
        an unknown RNB ID.
        Expected: each 200 response validates against the schema documented for its
        real Content-Type and is in the requested format (a Feature without root
        rnb_id for geojson, the building with its rnb_id for json), and the unknown
        RNB ID gives the documented 404.
        """
        single_doc = self.schema["paths"][SINGLE_PATH]["get"]

        for fmt in ("json", "geojson"):
            with self.subTest(format=fmt):
                r = self.client.get(
                    "/api/alpha/buildings/DOCEXAMPLE01/", {"format": fmt}
                )
                self.assertEqual(r.status_code, 200)
                self._validate_response(r, single_doc)
                data = r.json()
                if fmt == "geojson":
                    self.assertEqual(data["type"], "Feature")
                    self.assertEqual(data["id"], "DOCEXAMPLE01")
                    self.assertNotIn("rnb_id", data)
                else:
                    self.assertEqual(data["rnb_id"], "DOCEXAMPLE01")
                    self.assertNotIn("type", data)

        r = self.client.get("/api/alpha/buildings/UNKNOWNRNBID/")
        self.assertEqual(r.status_code, 404)
        self.assertIn("404", single_doc["responses"])
