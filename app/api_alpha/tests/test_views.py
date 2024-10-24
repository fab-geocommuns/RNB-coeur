import csv
import io
import json
from unittest import mock

from django.contrib.gis.geos import GEOSGeometry
from django.test import TransactionTestCase
from django.utils.http import urlencode
from rest_framework.test import APITestCase
from rest_framework_tracking.models import APIRequestLog

from batid.models import Building
from batid.models import Contribution
from batid.services.stats import compute_stats


class StatsTest(APITestCase):
    @mock.patch("batid.services.source.Source.default_ref")
    @mock.patch("api_alpha.views.requests.get")
    def test_stats(self, get_mock, default_src_ref_mock):

        # Mock the path to the cached stats file
        default_src_ref_mock.return_value = {
            "cached_stats": {"filename": "test_cached_stats.json"}
        }

        # create buildings for building count
        Building.objects.create(rnb_id="1", is_active=True)
        Building.objects.create(rnb_id="2", is_active=True)
        Building.objects.create(rnb_id="3", is_active=False)
        # trigger the stats computation for building count
        compute_stats()

        # create one contribution
        Contribution.objects.create()

        # log 2 API request, one is older than 2024
        APIRequestLog.objects.create(requested_at="2023-01-01T00:00:00Z")
        APIRequestLog.objects.create(requested_at="2024-01-02T00:00:00Z")

        # mock the data.gouv API
        get_mock.return_value.status_code = 200
        get_mock.return_value.json.return_value = {"total": 12}

        r = self.client.get("/api/alpha/stats")
        self.assertEqual(r.status_code, 200)
        results = r.json()

        self.assertEqual(results["building_counts"], 2)
        self.assertLess(results["building_counts"], 4)
        self.assertEqual(results["api_calls_since_2024_count"], 1)
        self.assertEqual(results["contributions_count"], 1)
        self.assertEqual(results["data_gouv_publication_count"], 11)

        # assert the mock was called
        get_mock.assert_called_with("https://www.data.gouv.fr/api/1/datasets/?tag=rnb")


class DiffTest(TransactionTestCase):
    def test_diff_create_update_delete(self):
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

        # create buildings
        b1 = Building.objects.create(rnb_id="1")
        # reload the buildings to get the sys_period
        treshold = Building.objects.get(rnb_id="1").sys_period.lower

        b2 = Building.objects.create(
            rnb_id="2",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
            event_type="creation",
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
        b3.event_type = "deletion"
        b3.save()

        # we want all the diff since the the creation of b1 (excluded)
        params = urlencode({"since": treshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        # parse the CSV response
        diff_text = get_content_from_streaming_response(r)
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

        # check the CSV file name
        b3 = Building.objects.get(rnb_id="3")
        most_recent_modification = b3.sys_period.lower
        expected_name = (
            f"diff_{treshold.isoformat()}_{most_recent_modification.isoformat()}.csv"
        )
        self.assertEqual(
            r["Content-Disposition"], f'attachment; filename="{expected_name}"'
        )

    def test_diff_merge(self):
        # create buildings
        b1 = Building.objects.create(
            rnb_id="1", status="constructed", event_type="creation"
        )
        b2 = Building.objects.create(
            rnb_id="2", status="constructed", event_type="creation"
        )
        Building.objects.create(rnb_id="t")
        # reload the buildings to get the sys_period
        treshold = Building.objects.get(rnb_id="t").sys_period.lower

        # merge buildings b1 and b2 into b3
        b1.event_type = "merge"
        b1.is_active = False
        b1.save()

        b2.event_type = "merge"
        b2.is_active = False
        b2.save()

        b3 = Building.objects.create(
            rnb_id="3", status="constructed", event_type="merge", is_active=True
        )

        # we want all the diff since the the creation of b1 (excluded)
        params = urlencode({"since": treshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        # parse the CSV response
        diff_text = get_content_from_streaming_response(r)
        reader = csv.reader(io.StringIO(diff_text))

        _headers = next(reader)

        # check the CSV content
        rows = list(reader)
        self.assertEqual(len(rows), 3)

        self.assertEqual(rows[0][0], "delete")
        self.assertEqual(rows[0][1], b1.rnb_id)
        self.assertEqual(rows[0][2], "constructed")

        self.assertEqual(rows[1][0], "delete")
        self.assertEqual(rows[1][1], b2.rnb_id)
        self.assertEqual(rows[1][2], "constructed")

        self.assertEqual(rows[2][0], "create")
        self.assertEqual(rows[2][1], b3.rnb_id)
        self.assertEqual(rows[2][2], "constructed")

    def test_diff_split(self):
        # create building
        b1 = Building.objects.create(rnb_id="1", status="constructed")
        Building.objects.create(rnb_id="t")
        # reload the buildings to get the sys_period
        treshold = Building.objects.get(rnb_id="t").sys_period.lower

        # split building b1 into b2 and b3
        b1.event_type = "split"
        b1.is_active = False
        b1.save()

        b2 = Building.objects.create(
            rnb_id="2", status="constructed", event_type="split", is_active=True
        )
        b3 = Building.objects.create(
            rnb_id="3", status="constructed", event_type="split", is_active=True
        )

        # we want all the diff since the the creation of b1 (excluded)
        params = urlencode({"since": treshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"

        r = self.client.get(url)

        diff_text = get_content_from_streaming_response(r)
        self.assertEqual(r.status_code, 200)

        reader = csv.reader(io.StringIO(diff_text))

        _headers = next(reader)

        # check the CSV content
        rows = list(reader)
        self.assertEqual(len(rows), 3)

        self.assertEqual(rows[0][0], "delete")
        self.assertEqual(rows[0][1], b1.rnb_id)
        self.assertEqual(rows[0][2], "constructed")

        self.assertEqual(rows[1][0], "create")
        self.assertEqual(rows[1][1], b2.rnb_id)
        self.assertEqual(rows[1][2], "constructed")

        self.assertEqual(rows[2][0], "create")
        self.assertEqual(rows[2][1], b3.rnb_id)
        self.assertEqual(rows[2][2], "constructed")

    def test_diff_no_since(self):
        # we want all the diff since the the creation of b1 (excluded)
        url = f"/api/alpha/buildings/diff/"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)

    def test_since_is_too_old(self):
        url = f"/api/alpha/buildings/diff/?since=2021-01-01T00:00:00Z"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)

    def test_since_is_invalid(self):
        url = f"/api/alpha/buildings/diff/?since=invalid"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)


class ContributionTest(APITestCase):
    def test_contribution(self):

        Building.objects.create(rnb_id="1")
        Contribution.objects.create(rnb_id="1", text="", email="riri@email.fr")

        data = {"email": "loulou@email.fr", "text": "test", "rnb_id": "1"}
        r = self.client.post("/api/alpha/contributions/", data)

        self.assertEqual(r.status_code, 201)
        self.assertEqual(Contribution.objects.count(), 2)
        # loulou is expected at the second place, ex aequo with fifi
        self.assertEqual(
            r.json(),
            {
                "rnb_id": "1",
                "text": "test",
                "email": "loulou@email.fr",
            },
        )

    # @freeze_time("2024-08-05")
    # def test_ranking(self):
    #     from batid.models import Department_subdivided
    #
    #     create_grenoble()
    #     create_paris()
    #
    #     Department_subdivided.objects.create(
    #         code="75",
    #         name="Paris",
    #         shape=GEOSGeometry(
    #             json.dumps(
    #                 {
    #                     "coordinates": [
    #                         [
    #                             [2.353306071148694, 48.90085197679912],
    #                             [2.298936023110457, 48.89580357010155],
    #                             [2.273133288448662, 48.87419062799353],
    #                             [2.2602319211170823, 48.84630219945575],
    #                             [2.313373267504062, 48.82102752865572],
    #                             [2.372965297558153, 48.81678013291423],
    #                             [2.4175057323916462, 48.84407854008418],
    #                             [2.411362224139367, 48.878837188722514],
    #                             [2.3907814714921187, 48.89964040569237],
    #                             [2.353306071148694, 48.90085197679912],
    #                         ]
    #                     ],
    #                     "type": "Polygon",
    #                 }
    #             ),
    #             srid=4326,
    #         ),
    #     )
    #
    #     Department_subdivided.objects.create(
    #         code="01",
    #         name="Ain",
    #         shape=GEOSGeometry(
    #             "POLYGON ((-1.1445170773446591 50.14048784607837, -1.1445170773446591 48.46067765220832, 2.180844882808316 48.46067765220832, 2.180844882808316 50.14048784607837, -1.1445170773446591 50.14048784607837))"
    #         ),
    #     )
    #
    #     Department_subdivided.objects.create(
    #         code="02",
    #         name="Aisne",
    #         shape=GEOSGeometry(
    #             "POLYGON ((4.023367285356358 49.55818275540048, 4.023367285356358 48.001809772072534, 7.459707468976717 48.001809772072534, 7.459707468976717 49.55818275540048, 4.023367285356358 49.55818275540048))"
    #         ),
    #     )
    #
    #     # Buildings in Paris
    #     Building.objects.create(
    #         rnb_id="p_1",
    #         point=GEOSGeometry("POINT (2.3151031002108637 48.853855939132494)"),
    #     )
    #     Building.objects.create(
    #         rnb_id="p_2",
    #         point=GEOSGeometry("POINT (2.366944834508937 48.87440863357778)"),
    #     )
    #
    #     # Contributions in Paris
    #     Contribution.objects.create(rnb_id="p_1", text="", email="lucie@dummy.fr")
    #     Contribution.objects.create(rnb_id="p_2", text="", email="lucie@dummy.fr")
    #
    #     # Buildings in Ain
    #     Building.objects.create(rnb_id="1_1", point=GEOSGeometry("POINT (0 49)"))
    #     Building.objects.create(rnb_id="1_2", point=GEOSGeometry("POINT (0 49)"))
    #     # Buildings in Aisne
    #     Building.objects.create(rnb_id="2_1", point=GEOSGeometry("POINT (5 49)"))
    #     Building.objects.create(rnb_id="2_2", point=GEOSGeometry("POINT (5 49)"))
    #
    #     # Contributions in Ain
    #     Contribution.objects.create(rnb_id="1_1", text="", email="riri@email.fr")
    #     Contribution.objects.create(rnb_id="1_2", text="", email="fifi@email.fr")
    #     Contribution.objects.create(rnb_id="1_2", text="", email="loulou@email.fr")
    #
    #     # Contributions in Aisne
    #     Contribution.objects.create(rnb_id="2_1", text="", email="riri@email.fr")
    #     Contribution.objects.create(rnb_id="2_2", text="", email="fifi@email.fr")
    #
    #     # refused contribution
    #     Contribution.objects.create(
    #         rnb_id="2_1", text="", email="riri@email.fr", status="refused"
    #     )
    #
    #     r = self.client.get("/api/alpha/contributions/ranking/")
    #     response = r.json()
    #
    #     self.assertEqual(r.status_code, 200)
    #     self.assertTrue("departement" in response)
    #     self.assertTrue("city" in response)
    #     self.assertTrue("individual" in response)
    #
    #     # individual ranking : [[count1, rank1], [count2, rank2], ...]
    #     # departement ranking : [[dpt_code1, dpt_name1, dpt_count1], [dpt_code2, dpt_name2, dpt_count2], ...]
    #     self.assertEqual(
    #         response,
    #         {
    #             "individual": [[2, 1], [2, 1], [2, 1], [1, 4]],
    #             "departement": [
    #                 ["01", "Ain", 3],
    #                 ["02", "Aisne", 2],
    #                 ["75", "Paris", 2],
    #             ],
    #             "city": [["75056", "Paris", 2]],
    #             "global": 7,
    #         },
    #     )

    def test_contribution_permissions_list(self):
        # you cannot list contributions
        r = self.client.get("/api/alpha/contributions/")
        self.assertEqual(r.status_code, 405)

    def test_contribution_permissions_read(self):
        Building.objects.create(rnb_id="xxx")
        c = Contribution.objects.create(rnb_id="xxx", text="", email="riri@email.fr")

        r = self.client.get(f"/api/alpha/contributions/{c.id}/")
        # you cannot access a contribution after it has been created
        # I was expecting a 405, but DRF is returning a 404
        self.assertEqual(r.status_code, 404)


def get_content_from_streaming_response(response):
    # streaming response content is a generator stored in streaming_content
    content = list(response.streaming_content)
    # each element of the list is a byte string, that we need to decode
    return "".join([b.decode("utf-8") for b in content])
