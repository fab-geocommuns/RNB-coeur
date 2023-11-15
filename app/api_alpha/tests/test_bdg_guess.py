from rest_framework.test import APITestCase

from batid.models import BuildingStatus
from batid.tests.helpers import create_bdg


class BdgGuessEndpointTest(APITestCase):
    def setUp(self):
        b = create_bdg(
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

        BuildingStatus.objects.create(building=b, type="constructed", is_current=True)

    def test_point_param(self):
        r = self.client.get(
            "/api/alpha/buildings/guess/?point=45.184327114924656,5.721176133001023"
        )

        self.assertEqual(r.status_code, 200)

        expected = [
            {
                "addresses": [],
                "score": 1.0,
                "ext_bdtopo_id": None,
                "point": {
                    "coordinates": [5.721181338205954, 45.18433384981944],
                    "type": "Point",
                },
                "rnb_id": "DUMMYDUMMYGO",
                "status": [
                    {
                        "happened_at": None,
                        "is_current": True,
                        "label": "Construit",
                        "type": "constructed",
                    }
                ],
            }
        ]

        self.assertListEqual(r.json(), expected)
