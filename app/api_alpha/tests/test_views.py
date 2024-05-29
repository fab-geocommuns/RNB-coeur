from unittest import mock

from django.test import TransactionTestCase
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog

from batid.models import Building
from batid.models import Contribution


class StatsTest(APITestCase):
    @mock.patch("api_alpha.views.requests.get")
    def test_stats(self, get_mock):
        # create 2 buldings
        Building.objects.create(rnb_id="1")
        Building.objects.create(rnb_id="2")

        # create one contribution
        Contribution.objects.create()

        # log 2 API request, one is older than 2024
        APIRequestLog.objects.create(requested_at="2023-01-01T00:00:00Z")
        APIRequestLog.objects.create(requested_at="2024-01-02T00:00:00Z")

        # # count the number of buildings to update the estimate in the DB
        Building.objects.count()

        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {"total": 12}

        r = self.client.get("/api/alpha/stats")

        self.assertEqual(r.status_code, 200)
        results = r.json()
        # assert building_counts is in a range, because it's an estimate
        self.assertGreaterEqual(results["building_counts"], -2)
        self.assertLess(results["building_counts"], 4)
        self.assertEqual(results["api_calls_since_2024_count"], 1)
        self.assertEqual(results["contributions_count"], 1)
        self.assertEqual(results["data_gouv_publication_count"], 11)

        # assert the mock was called
        get_mock.assert_called_with("https://www.data.gouv.fr/api/1/datasets/?tag=rnb")


class DiffTest(TransactionTestCase):
    def test_diff(self):
        from django.utils.http import urlencode
        import csv
        import io
        from django.contrib.gis.geos import GEOSGeometry
        import json

        coords = {
            "coordinates": [
                [
                    [
                        [1.0654705955877262, 46.63423852982024],
                        [1.065454930919401, 46.634105152847496],
                        [1.0656648374661017, 46.63409009413692],
                        [1.0656773692001593, 46.63422131990677],
                        [1.0654705955877262, 46.63423852982024],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }
        geom = GEOSGeometry(json.dumps(coords), srid=4326)

        b = Building.objects.create(
            rnb_id="BDGSRNBBIDID",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
        )

        # create buildings
        b1 = Building.objects.create(rnb_id="1")
        # reload the buildings to get the sys_period
        treshold = Building.objects.get(rnb_id="1").sys_period.lower

        b2 = Building.objects.create(
            rnb_id="2", shape=geom, point=geom.point_on_surface, status="constructed"
        )
        b3 = Building.objects.create(
            rnb_id="3", shape=geom, point=geom.point_on_surface, status="constructed"
        )

        # update a building
        b1.status = "demolished"
        b1.event_type = "update"
        b1.save()

        # soft delete a building
        b3.is_active = False
        b3.event_type = "delete"
        b3.save()

        # we want all the diff since the the creation of b1 (excluded)
        params = urlencode({"since": treshold.isoformat()})
        url = f"/api/alpha/diff?{params}"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        # parse the CSV response
        diff_text = r.content.decode("utf-8")
        reader = csv.reader(io.StringIO(diff_text))

        # check the CSV header
        header = next(reader)
        self.assertEqual(
            header,
            [
                "action",
                "rnb_id",
                "status",
                "sys_period",
                "point",
                "shape",
                "addresses_id",
                "ext_ids",
            ],
        )

        # check the CSV content
        rows = list(reader)
        self.assertEqual(len(rows), 4)

        self.assertEqual(rows[0][0], "update")
        self.assertEqual(rows[0][1], b1.rnb_id)
        self.assertEqual(rows[0][2], "demolished")

        self.assertEqual(rows[1][0], "create")
        self.assertEqual(rows[1][1], b2.rnb_id)
        self.assertEqual(rows[1][2], "constructed")
        self.assertRegex(rows[1][4], r"SRID=4326;POINT\(\d+\.\d+ \d+\.\d+\)")
        self.assertRegex(rows[1][5], r"SRID=4326;MULTIPOLYGON\(.+\)")

        self.assertEqual(rows[2][0], "create")
        self.assertEqual(rows[2][1], b3.rnb_id)
        self.assertEqual(rows[2][2], "constructed")

        self.assertEqual(rows[3][0], "delete")
        self.assertEqual(rows[3][1], b3.rnb_id)
        self.assertEqual(rows[3][2], "constructed")

    def test_diff_no_since(self):
        # we want all the diff since the the creation of b1 (excluded)
        url = f"/api/alpha/diff"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)

    def test_since_is_too_old(self):
        url = f"/api/alpha/diff?since=2021-01-01T00:00:00Z"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)

    def test_since_is_invalid(self):
        url = f"/api/alpha/diff?since=invalid"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)
