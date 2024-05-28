from unittest import mock

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


class DiffTest(APITestCase):
    def test_diff(self):
        from django.utils.http import urlencode
        import csv
        import io

        # create 2 buldings
        b1 = Building.objects.create(rnb_id="1")
        b2 = Building.objects.create(rnb_id="2")

        params = urlencode({"since": b1.sys_period.lower.isoformat()})
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
                "sys_period",
                "point",
                "shape",
                "addresses_id",
                "ext_ids",
            ],
        )

        # check the CSV content
        rows = list(reader)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0], [b1.rnb_id, "sys_period", b1.sys_period.lower.isoformat(), None]
        )
