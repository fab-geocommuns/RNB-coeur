from batid.models import Building
from rest_framework.test import APITestCase

# Côté du carré d'input : 2^-8 degré (~434 m), exact en binaire pour que les
# ratios d'aires calculés en SQL tombent juste.
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
        Input: un carré de côté H (~434 m) en WKT ; un bâtiment de côté H/2
        entièrement inclus dans l'input, un bâtiment de côté H chevauchant l'input
        sur un carré H/2, et un bâtiment hors de l'input.
        Attendu: 200 ; seuls les deux bâtiments intersectants, triés par IoU
        décroissant, chacun avec iou, input_covered_by_rnb et rnb_covered_by_input
        arrondis à 3 décimales, et les champs standard d'un bâtiment (rnb_id, shape).
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
        Input: un carré de côté H ; trois bâtiments entièrement inclus dedans,
        l'un démoli, l'autre inactif, le dernier réel
        Attendu: 200 ; seul le bâtiment réel est renvoyé.
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
        Input: un carré de côté H ; un bâtiment surfacique inclus dans l'input,
        un bâtiment dont la géométrie est un simple point situé dans l'input,
        et un bâtiment "point seul" situé hors de l'input.
        Attendu: 200 ; le bâtiment surfacique d'abord, puis le point-dans-l'input
        avec iou, input_covered_by_rnb et rnb_covered_by_input à null ;
        le point hors input est absent.
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

    def test_3d_polygon_is_treated_as_its_2d_projection(self):
        """
        Input: un carré 3D (POLYGON Z, z=10) de côté H ; un bâtiment de côté H/2
        entièrement inclus dans la projection 2D de l'input.
        Attendu: 200 ; la coordonnée z est ignorée, le bâtiment est renvoyé avec
        les mêmes métriques que pour l'input 2D équivalent (iou 0.25).
        """
        inside = Building.objects.create(
            rnb_id="bdg_inside",
            shape=square(0, 0, H_HALF, H_HALF),
        )
        inside.point = inside.shape.point_on_surface
        inside.save()

        input_square_3d = f"POLYGON Z((0 0 10, 0 {H} 10, {H} {H} 10, {H} 0 10, 0 0 10))"
        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": input_square_3d},
        )

        self.assertEqual(r.status_code, 200)
        [r1] = r.json()["results"]
        self.assertEqual(r1["rnb_id"], "bdg_inside")
        self.assertEqual(r1["iou"], 0.25)
        self.assertEqual(r1["input_covered_by_rnb"], 0.25)
        self.assertEqual(r1["rnb_covered_by_input"], 1.0)

    def test_adjoining_building_is_listed_with_zero_metrics(self):
        """
        Input: la copie exacte de l'emprise du premier de deux bâtiments
        rectangulaires mitoyens (ils partagent une arête, donc deux coins).
        Attendu: 200 ; les deux bâtiments sont listés, le bâtiment copié en
        premier avec des métriques à 1, le mitoyen ensuite avec iou,
        input_covered_by_rnb et rnb_covered_by_input à 0.
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
        Input: un carré de côté H ; un bâtiment entièrement inclus dedans.
        Attendu: 200 ; le résultat expose exactement les champs standard d'un
        bâtiment (comme sur buildings/) plus les trois métriques d'intersection.
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
        Input: requête sans paramètre shape.
        Attendu: 400.
        """
        r = self.client.get("/api/alpha/buildings/intersect/")
        self.assertEqual(r.status_code, 400)

    def test_unparseable_wkt_is_rejected(self):
        """
        Input: shape="coucou", qui n'est pas du WKT.
        Attendu: 400.
        """
        r = self.client.get("/api/alpha/buildings/intersect/", {"shape": "coucou"})
        self.assertEqual(r.status_code, 400)

    def test_non_polygon_geometries_are_rejected(self):
        """
        Input: shape en WKT valide mais de type Point puis MultiPolygon.
        Attendu: 400 pour chacun, seul le type Polygon est accepté.
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
        Input: shape en WKT de type Polygon mais auto-intersectant (papillon).
        Attendu: 400.
        """
        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": f"POLYGON((0 0, {H} {H}, {H} 0, 0 {H}, 0 0))"},
        )
        self.assertEqual(r.status_code, 400)

    def test_non_wgs84_srid_is_rejected(self):
        """
        Input: shape en EWKT déclarant explicitement un SRID autre que 4326
        (SRID=3857).
        Attendu: 400, le polygone doit être exprimé en WGS84.
        """
        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": f"SRID=3857;POLYGON((0 0, 0 {H}, {H} {H}, {H} 0, 0 0))"},
        )
        self.assertEqual(r.status_code, 400)

    def test_too_large_polygon_is_rejected(self):
        """
        Input: un carré de 1x1 degré (~12 000 km²), très au-delà du 1 km² maximal.
        Attendu: 400.
        """
        r = self.client.get(
            "/api/alpha/buildings/intersect/",
            {"shape": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))"},
        )
        self.assertEqual(r.status_code, 400)

    def test_results_are_paginated(self):
        """
        Input: un carré de côté H contenant deux bâtiments, requête avec limit=1.
        Attendu: 200 ; enveloppe {next, previous, results} avec un seul résultat
        et un lien next ; la page 2 contient le second bâtiment.
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
