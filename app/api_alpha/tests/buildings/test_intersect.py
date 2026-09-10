from batid.models import Building
from rest_framework.test import APITestCase

# Side of the input square: 2^-8 degree (~434 m), exact in binary so that the
# area ratios computed in SQL come out to round values.
H = 0.00390625
H_HALF = H / 2
H_1_5 = 3 * H / 2

INPUT_SQUARE = f"POLYGON((0 0, 0 {H}, {H} {H}, {H} 0, 0 0))"


def square(x_min, y_min, x_max, y_max):
    return (
        f"POLYGON(({x_min} {y_min}, {x_min} {y_max}, {x_max} {y_max}, "
        f"{x_max} {y_min}, {x_min} {y_min}))"
    )


class BuildingIntersectViewTest(APITestCase):
    def test_buildings_intersecting_polygon_sorted_by_iou(self):
        """
        Input: a WKT square of side H (~434 m); a building of side H/2 entirely
        inside the input, a building of side H overlapping the input on a H/2
        square, and a building outside the input.
        Expected: 200; only the two intersecting buildings, sorted by decreasing
        IoU, each with iou, input_covered_by_rnb and rnb_covered_by_input rounded
        to 3 decimals, plus the standard building fields (rnb_id, shape).
        """
        inside = Building.objects.create(
            rnb_id="bdg_inside",
            shape=square(0, 0, H_HALF, H_HALF),
        )
        inside.point = inside.shape.point_on_surface
        inside.save()

        overlapping = Building.objects.create(
            rnb_id="bdg_overlap",
            shape=square(H_HALF, H_HALF, H_1_5, H_1_5),
        )
        overlapping.point = overlapping.shape.point_on_surface
        overlapping.save()

        away = Building.objects.create(
            rnb_id="bdg_away",
            shape=square(1, 1, 1 + H, 1 + H),
        )
        away.point = away.shape.point_on_surface
        away.save()

        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": INPUT_SQUARE},
        )

        self.assertEqual(r.status_code, 200)
        data = r.json()

        [r1, r2] = data["results"]

        # inside: intersection 0.25, union 1.0
        self.assertEqual(r1["rnb_id"], "bdg_inside")
        self.assertEqual(r1["iou"], 0.25)
        self.assertEqual(r1["input_covered_by_rnb"], 0.25)
        self.assertEqual(r1["rnb_covered_by_input"], 1.0)
        self.assertEqual(r1["shape"]["type"], "Polygon")

        # overlapping: intersection 0.25, union 1.75
        self.assertEqual(r2["rnb_id"], "bdg_overlap")
        self.assertEqual(r2["iou"], 0.143)
        self.assertEqual(r2["input_covered_by_rnb"], 0.25)
        self.assertEqual(r2["rnb_covered_by_input"], 0.25)

    def test_only_real_buildings(self):
        """
        Input: a square of side H; three buildings entirely inside it, one
        demolished, one inactive, the last one real.
        Expected: 200; only the real building is returned.
        """
        demolished = Building.objects.create(
            rnb_id="bdg_demol",
            shape=square(0, 0, H_HALF, H_HALF),
            status="demolished",
        )
        demolished.point = demolished.shape.point_on_surface
        demolished.save()

        inactive = Building.objects.create(
            rnb_id="bdg_inactive",
            shape=square(0, 0, H_HALF, H_HALF),
            is_active=False,
        )
        inactive.point = inactive.shape.point_on_surface
        inactive.save()

        real = Building.objects.create(
            rnb_id="bdg_real",
            shape=square(0, 0, H_HALF, H_HALF),
        )
        real.point = real.shape.point_on_surface
        real.save()

        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": INPUT_SQUARE},
        )

        self.assertEqual(r.status_code, 200)
        results = r.json()["results"]
        self.assertEqual([b["rnb_id"] for b in results], ["bdg_real"])

    def test_point_only_building_has_null_metrics_and_comes_last(self):
        """
        Input: a square of side H; a surface building inside the input, a
        building whose geometry is a mere point located inside the input, and a
        "point only" building located outside the input.
        Expected: 200; the surface building first, then the point-inside-the-input
        one with iou, input_covered_by_rnb and rnb_covered_by_input set to null;
        the point outside the input is absent.
        """
        surfacic = Building.objects.create(
            rnb_id="bdg_surfacic",
            shape=square(0, 0, H_HALF, H_HALF),
        )
        surfacic.point = surfacic.shape.point_on_surface
        surfacic.save()

        Building.objects.create(
            rnb_id="bdg_pt_in",
            shape=f"POINT({H_HALF} {H_HALF})",
            point=f"POINT({H_HALF} {H_HALF})",
        )

        Building.objects.create(
            rnb_id="bdg_pt_out",
            shape="POINT(1 1)",
            point="POINT(1 1)",
        )

        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": INPUT_SQUARE},
        )

        self.assertEqual(r.status_code, 200)
        [r1, r2] = r.json()["results"]

        self.assertEqual(r1["rnb_id"], "bdg_surfacic")

        self.assertEqual(r2["rnb_id"], "bdg_pt_in")
        self.assertIsNone(r2["iou"])
        self.assertIsNone(r2["input_covered_by_rnb"])
        self.assertIsNone(r2["rnb_covered_by_input"])

    def test_3d_polygon_is_rejected(self):
        """
        Input: a 3D square (POLYGON Z, z=10) of side H, as exported by some GIS.
        Expected: 400 with an explicit 3D message, consistently with the other
        endpoints taking a geometry as input, which refuse 3D geometries.
        """
        input_square_3d = f"POLYGON Z((0 0 10, 0 {H} 10, {H} {H} 10, {H} 0 10, 0 0 10))"
        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": input_square_3d},
        )

        self.assertEqual(r.status_code, 400)
        self.assertIn("3D", str(r.json()))

    def test_adjoining_building_is_listed_with_zero_metrics(self):
        """
        Input: the exact copy of the footprint of the first of two adjoining
        rectangular buildings (they share an edge, hence two corners).
        Expected: 200; both buildings are listed, the copied one first with
        metrics at 1, the adjoining one next with iou, input_covered_by_rnb and
        rnb_covered_by_input at 0.
        """
        target = Building.objects.create(
            rnb_id="bdg_target",
            shape=square(0, 0, H_HALF, H_HALF),
        )
        target.point = target.shape.point_on_surface
        target.save()

        adjoining = Building.objects.create(
            rnb_id="bdg_adjoin",
            shape=square(H_HALF, 0, H, H_HALF),
        )
        adjoining.point = adjoining.shape.point_on_surface
        adjoining.save()

        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": square(0, 0, H_HALF, H_HALF)},
        )

        self.assertEqual(r.status_code, 200)
        [r1, r2] = r.json()["results"]

        self.assertEqual(r1["rnb_id"], "bdg_target")
        self.assertEqual(r1["iou"], 1.0)
        self.assertEqual(r1["input_covered_by_rnb"], 1.0)
        self.assertEqual(r1["rnb_covered_by_input"], 1.0)

        self.assertEqual(r2["rnb_id"], "bdg_adjoin")
        self.assertEqual(r2["iou"], 0.0)
        self.assertEqual(r2["input_covered_by_rnb"], 0.0)
        self.assertEqual(r2["rnb_covered_by_input"], 0.0)

    def test_result_contains_all_expected_building_fields(self):
        """
        Input: a square of side H; a building entirely inside it.
        Expected: 200; the result exposes exactly the standard building fields
        (as on buildings/) plus the three intersection metrics.
        """
        inside = Building.objects.create(
            rnb_id="bdg_inside",
            shape=square(0, 0, H_HALF, H_HALF),
        )
        inside.point = inside.shape.point_on_surface
        inside.save()

        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": INPUT_SQUARE},
        )

        self.assertEqual(r.status_code, 200)
        [r1] = r.json()["results"]
        self.assertCountEqual(
            r1.keys(),
            [
                "rnb_id",
                "point",
                "shape",
                "status",
                "is_active",
                "addresses",
                "ext_ids",
                "validated_by",
                "iou",
                "input_covered_by_rnb",
                "rnb_covered_by_input",
            ],
        )

    def test_shape_param_is_required(self):
        """
        Input: request without the shape parameter.
        Expected: 400.
        """
        r = self.client.get("/api/alpha/buildings/intersect/")
        self.assertEqual(r.status_code, 400)

    def test_unparseable_wkt_is_rejected(self):
        """
        Input: shape="coucou", which is not WKT.
        Expected: 400.
        """
        r = self.client.get("/api/alpha/buildings/intersect/", {"shape": "coucou"})
        self.assertEqual(r.status_code, 400)

    def test_non_polygon_geometries_are_rejected(self):
        """
        Input: valid WKT shape, of type Point then MultiPolygon.
        Expected: 400 for each, only the Polygon type is accepted.
        """
        r = self.client.get("/api/alpha/buildings/intersect/", {"shape": "POINT(0 0)"})
        self.assertEqual(r.status_code, 400)

        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": f"MULTIPOLYGON(((0 0, 0 {H}, {H} {H}, {H} 0, 0 0)))"},
        )
        self.assertEqual(r.status_code, 400)

    def test_invalid_polygon_is_rejected(self):
        """
        Input: WKT shape of type Polygon but self-intersecting (butterfly).
        Expected: 400.
        """
        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": f"POLYGON((0 0, {H} {H}, {H} 0, 0 {H}, 0 0))"},
        )
        self.assertEqual(r.status_code, 400)

    def test_non_wgs84_srid_is_rejected(self):
        """
        Input: EWKT shape explicitly declaring a SRID other than 4326
        (SRID=3857).
        Expected: 400, the polygon must be expressed in WGS84.
        """
        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": f"SRID=3857;POLYGON((0 0, 0 {H}, {H} {H}, {H} 0, 0 0))"},
        )
        self.assertEqual(r.status_code, 400)

    def test_too_large_polygon_is_rejected(self):
        """
        Input: a 1x1 degree square (~12,000 km²), far beyond the 1 km² maximum.
        Expected: 400.
        """
        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))"},
        )
        self.assertEqual(r.status_code, 400)

    def test_results_are_paginated(self):
        """
        Input: a square of side H containing two buildings, request with limit=1.
        Expected: 200; {next, previous, results} envelope with a single result
        and a next link; page 2 contains the second building.
        """
        first = Building.objects.create(
            rnb_id="bdg_first",
            shape=square(0, 0, H_HALF, H_HALF),
        )
        first.point = first.shape.point_on_surface
        first.save()

        second = Building.objects.create(
            rnb_id="bdg_second",
            shape=square(0, 0, H_HALF, H_HALF),
        )
        second.point = second.shape.point_on_surface
        second.save()

        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": INPUT_SQUARE, "limit": 1},
        )

        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["rnb_id"], "bdg_first")
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

        r2 = self.client.get(data["next"])
        self.assertEqual(r2.status_code, 200)
        data2 = r2.json()
        self.assertEqual(data2["results"][0]["rnb_id"], "bdg_second")
