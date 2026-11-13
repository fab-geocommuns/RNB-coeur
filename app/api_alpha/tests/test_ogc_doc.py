"""
Tests checking that the documentation of the OGC endpoints matches what they really do.
"""

from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from batid.models import Building, City, Plot
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from rest_framework.test import APITestCase

# Two buildings a few meters away from each other, inside the test city
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


class OGCDocTest(APITestCase):
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
        City.objects.create(
            code_insee="33063",
            name="Bordeaux",
            shape=MultiPolygon(POLYGONS[0].buffer(0.01), srid=4326),
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

    def _get(self, url: str, params: dict | None = None):
        return self.client.get(url, params or {})

    # ---------- OGC

    def test_ogc_operations_have_unique_ids(self):
        """
        Input: every documented OGC operation.
        Expected: each one has an operationId, and no id is used twice in the schema.
        """
        all_ids = []
        for path, path_item in self.schema["paths"].items():
            for operation in path_item.values():
                if "/ogc" in path:
                    self.assertIn("operationId", operation, path)
                if "operationId" in operation:
                    all_ids.append(operation["operationId"])
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_ogc_bbox_is_serialized_as_one_value(self):
        """
        Input: a building at the center of the documented OGC bbox example, then the
        example serialized the way its style says (explode false: one
        comma-separated value), then exploded.
        Expected: the documented serialization returns only that building, the
        exploded one is refused.
        """
        path, _ = self._operation("ogcBuildingItems")
        bbox = self._params("ogcBuildingItems")["bbox"]
        self.assertFalse(bbox["explode"])

        values = bbox["example"]
        self.assertEqual(len(values), bbox["schema"]["minItems"])
        min_lng, min_lat, max_lng, max_lat = values
        center = GEOSGeometry(
            f"POINT({(min_lng + max_lng) / 2} {(min_lat + max_lat) / 2})", srid=4326
        )
        Building.objects.create(
            rnb_id="INEXAMPLEBOX",
            shape=center,
            point=center,
            status="constructed",
            ext_ids=[],
        )

        r = self._get(path, {"bbox": ",".join(str(v) for v in values)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([f["id"] for f in r.json()["features"]], ["INEXAMPLEBOX"])

        r = self.client.get(path + "?" + "&".join(f"bbox={v}" for v in values))
        self.assertEqual(r.status_code, 400)

    def test_ogc_items_return_real_buildings_by_default(self):
        """
        Input: a demolished building next to the two constructed ones, listed
        without status, then with status=demolished.
        Expected: by default only the constructed buildings are returned, as the
        description says; the status parameter can still return the demolished one,
        hence the "by default" in the description.
        """
        path, _ = self._operation("ogcBuildingItems")
        lng, lat = CLOSEST_POINT[1], CLOSEST_POINT[0]
        point = GEOSGeometry(f"POINT({lng + 0.0005} {lat})", srid=4326)
        Building.objects.create(
            rnb_id="DEMOLISHED00",
            shape=point,
            point=point,
            status="demolished",
            ext_ids=[],
        )
        bbox = f"{lng - 0.01},{lat - 0.01},{lng + 0.01},{lat + 0.01}"

        r = self._get(path, {"bbox": bbox})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            sorted(f["id"] for f in r.json()["features"]),
            ["CLOSEST00000", "CLOSEST00001"],
        )

        r = self._get(path, {"bbox": bbox, "status": "demolished"})
        self.assertEqual([f["id"] for f in r.json()["features"]], ["DEMOLISHED00"])

    def test_ogc_with_plots_and_insee_code(self):
        """
        Input: OGC items and OGC item with withPlots=1, then OGC items on the test
        city INSEE code, on an unknown one and on codes of 4 and 6 characters.
        Expected: withPlots is documented on both operations and adds the plots to
        the properties; the city filter returns its buildings, an unknown INSEE code
        gives the documented 404, a code without 5 characters the documented 400.
        """
        items_path, items_doc = self._operation("ogcBuildingItems")
        item_path, _ = self._operation("ogcBuildingItem")
        for operation_id in ("ogcBuildingItems", "ogcBuildingItem"):
            self.assertIn("withPlots", self._params(operation_id))

        r = self._get(items_path, {"insee_code": "33063", "withPlots": "1"})
        self.assertEqual(r.status_code, 200)
        features = r.json()["features"]
        self.assertEqual(len(features), len(POLYGONS))
        self.assertIn("plots", features[0]["properties"])

        r = self._get(
            item_path.replace("{featureId}", "CLOSEST00000"), {"withPlots": "1"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("plots", r.json()["properties"])

        r = self._get(items_path, {"insee_code": "99999"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("404", items_doc["responses"])

        insee_schema = self._params("ogcBuildingItems")["insee_code"]["schema"]
        self.assertEqual((insee_schema["minLength"], insee_schema["maxLength"]), (5, 5))
        for code in ("3306", "330630"):
            r = self._get(items_path, {"insee_code": code})
            self.assertEqual(r.status_code, 400)
        self.assertIn("400", items_doc["responses"])
