from rest_framework.test import APITestCase

from batid.tests.helpers import create_constructed_bdg
from django.contrib.gis.geos import Point


class BdgGuessEndpointTest(APITestCase):
    def setUp(self):
        b = create_constructed_bdg(
            "DUMMYDUMMYGO",
            [
                [5.721187072129851, 45.18439363812283],
                [5.721094925229238, 45.184330511384644],
                [5.721122483180295, 45.184274061453465],
                [5.721241326846666, 45.18428316628476],
                [5.721244771590875, 45.184325048490564],
                [5.7212697459849835, 45.18433718825423],
                [5.721187072129851, 45.18439363812283],
            ],
        )

    def test_point_param(self):
        r = self.client.get(
            "/api/alpha/buildings/guess/?point=45.184327114924656,5.721176133001023"
        )

        self.assertEqual(r.status_code, 200)

        expected = [
            {
                "addresses": [],
                "score": 5.0,
                "sub_scores": {"point_distance": 5, "point_plot_cluster": 0},
                "ext_ids": None,
                "status": "constructed",
                "point": {
                    "coordinates": [5.721181338205954, 45.18433384981944],
                    "type": "Point",
                },
                "rnb_id": "DUMMYDUMMYGO",
            }
        ]

        self.assertListEqual(r.json(), expected)


class DistanceComputation(APITestCase):
    def test_distance_computation(self):
        a = Point(873000, 6572000, srid=2154)
        b = Point(873100, 6572000, srid=2154)

        # real distance
        self.assertEqual(a.distance(b), 100)

        a = a.transform(4326, clone=True)
        b = b.transform(4326, clone=True)

        from batid.services.guess_bdg import compute_distance

        dist = compute_distance(a, b)

        self.assertAlmostEqual(dist, 100, delta=1)
