import csv
import datetime
import io
import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from django.test import TransactionTestCase
from django.utils.http import urlencode

from batid.models import Address
from batid.models import Building
from batid.models import City
from batid.models import Organization
from batid.models import UserProfile


def get_content_from_streaming_response(response):
    # streaming response content is a generator stored in streaming_content
    content = list(response.streaming_content)
    # each element of the list is a byte string, that we need to decode
    return "".join([b.decode("utf-8") for b in content])


class DiffTest(TransactionTestCase):
    def setUp(self):
        # We need a user for all building operations
        # We also need an organization for transparency
        user = User.objects.create_user(
            first_name="Marcella", last_name="Paviollon", username="marcella"
        )
        UserProfile.objects.create(user=user)
        org = Organization.objects.create(name="Mairie Marseille")
        org.users.add(user)

        # We need some addresses
        Address.objects.create(id="ADDRESS_ID_1")
        Address.objects.create(id="ADDRESS_ID_2")
        Address.objects.create(id="ADDRESS_ID_3")

    def test_diff_create_update_deactivate(self):

        # Get the user
        user = User.objects.get(username="marcella")

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

        # #############
        # First building
        b1 = Building.objects.create(
            rnb_id="1",
            ext_ids=[
                {
                    "source": "test",
                    "source_version": "11_2024",
                    "id": "1",
                    "created_at": "2024-08-05T00:00:00Z",
                }
            ],
            addresses_id=["ADDRESS_ID_1"],
            event_type="creation",
        )
        # reload the buildings to get the sys_period
        treshold = Building.objects.get(rnb_id="1").sys_period.lower

        # We update its status
        b1.update(
            status="demolished",
            user=user,
            event_origin={"source": "test"},
            addresses_id=["ADDRESS_ID_2", "ADDRESS_ID_3"],
        )

        # #############
        # Second building
        b2 = Building.objects.create(
            rnb_id="2",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
            event_type="creation",
        )
        # We do nothing else on the second building

        # #############
        # Third building
        b3 = Building.objects.create(
            rnb_id="3",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
            event_type="creation",
        )
        b3.deactivate(user=user, event_origin={"source": "test"})

        # we want all the diff since the creation of b1 (excluded)
        params = urlencode({"since": treshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        # parse the CSV response
        diff_text = get_content_from_streaming_response(r)
        reader = csv.DictReader(io.StringIO(diff_text))

        # check the CSV header
        self.assertListEqual(
            list(reader.fieldnames),
            [
                "action",
                "rnb_id",
                "status",
                "is_active",
                "sys_period",
                "point",
                "shape",
                "addresses_id",
                "ext_ids",
                "parent_buildings",
                "event_id",
                "event_type",
            ],
        )

        # check the CSV content
        rows = list(reader)

        self.assertEqual(len(rows), 4)

        self.assertEqual(rows[0]["action"], "update")
        self.assertEqual(rows[0]["rnb_id"], b1.rnb_id)
        self.assertEqual(rows[0]["status"], "demolished")
        self.assertEqual(rows[0]["is_active"], "1")
        self.assertListEqual(
            json.loads(rows[0]["ext_ids"]),
            [
                {
                    "source": "test",
                    "source_version": "11_2024",
                    "id": "1",
                    "created_at": "2024-08-05T00:00:00Z",
                }
            ],
        )
        self.assertListEqual(
            json.loads(rows[0]["addresses_id"]), ["ADDRESS_ID_2", "ADDRESS_ID_3"]
        )

        self.assertEqual(rows[1]["action"], "create")
        self.assertEqual(rows[1]["rnb_id"], b2.rnb_id)
        self.assertEqual(rows[1]["status"], "constructed")
        self.assertRegex(rows[1]["point"], r"SRID=4326;POINT\(\d+\.\d+ \d+\.\d+\)")
        self.assertRegex(rows[1]["shape"], r"SRID=4326;MULTIPOLYGON\(.+\)")

        self.assertEqual(rows[2]["action"], "create")
        self.assertEqual(rows[2]["rnb_id"], b3.rnb_id)
        self.assertEqual(rows[2]["status"], "constructed")

        self.assertEqual(rows[3]["action"], "deactivate")
        self.assertEqual(rows[3]["rnb_id"], b3.rnb_id)
        self.assertEqual(rows[3]["status"], "constructed")

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

        # Get the user
        user = User.objects.get(username="marcella")
        # Shape for buildings
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
        b1 = Building.objects.create(
            rnb_id="1",
            status="constructed",
            event_type="creation",
            addresses_id=["ADDRESS_ID_1"],
            shape=geom,
            point=geom.point_on_surface,
        )
        b2 = Building.objects.create(
            rnb_id="2",
            status="constructed",
            event_type="creation",
            addresses_id=["ADDRESS_ID_2"],
            shape=geom,
            point=geom.point_on_surface,
        )
        Building.objects.create(rnb_id="t", event_type="creation")
        # reload the buildings to get the sys_period
        treshold = Building.objects.get(rnb_id="t").sys_period.lower

        b3 = Building.merge(
            [b1, b2],
            user=user,
            event_origin={"source": "dummy"},
            addresses_id=["ADDRESS_ID_1", "ADDRESS_ID_2"],
            status="constructed",
        )

        # we want all the diff since the creation of b1 (excluded)
        params = urlencode({"since": treshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        # parse the CSV response
        diff_text = get_content_from_streaming_response(r)

        reader = csv.DictReader(io.StringIO(diff_text))
        rows = list(reader)

        self.assertEqual(len(rows), 3)

        # #####
        # first parent
        self.assertEqual(rows[0]["action"], "deactivate")
        self.assertEqual(rows[0]["rnb_id"], b1.rnb_id)
        self.assertEqual(rows[0]["status"], "constructed")
        self.assertEqual(rows[0]["is_active"], "0")
        self.assertListEqual(json.loads(rows[0]["addresses_id"]), ["ADDRESS_ID_1"])
        self.assertListEqual(json.loads(rows[0]["ext_ids"]), [])
        self.assertEqual(rows[0]["parent_buildings"], "")
        self.assertEqual(rows[0]["event_type"], "merge")

        # #####
        # second parent
        self.assertEqual(rows[1]["action"], "deactivate")
        self.assertEqual(rows[1]["rnb_id"], b2.rnb_id)
        self.assertEqual(rows[1]["status"], "constructed")
        self.assertEqual(rows[1]["is_active"], "0")
        self.assertListEqual(json.loads(rows[1]["addresses_id"]), ["ADDRESS_ID_2"])
        self.assertListEqual(json.loads(rows[1]["ext_ids"]), [])
        self.assertEqual(rows[1]["parent_buildings"], "")
        self.assertEqual(rows[1]["event_type"], "merge")
        # event_id: we check the three rows share the same event_id
        self.assertEqual(rows[1]["event_id"], rows[0]["event_id"])

        # #####
        # This row is the result of the merge
        self.assertEqual(rows[2]["action"], "create")
        self.assertEqual(rows[2]["rnb_id"], b3.rnb_id)
        self.assertEqual(rows[2]["status"], "constructed")
        self.assertEqual(rows[2]["is_active"], "1")
        self.assertListEqual(
            json.loads(rows[2]["addresses_id"]), ["ADDRESS_ID_1", "ADDRESS_ID_2"]
        )
        self.assertListEqual(json.loads(rows[2]["ext_ids"]), [])
        self.assertListEqual(
            json.loads(rows[2]["parent_buildings"]), [b1.rnb_id, b2.rnb_id]
        )
        self.assertEqual(rows[2]["event_type"], "merge")
        # event_id: we check the three rows share the same event_id
        self.assertEqual(rows[2]["event_id"], rows[0]["event_id"])

    @override_settings(MAX_BUILDING_AREA=float("inf"), BUILDING_OVERLAP_THRESHOLD=1.1)
    def test_diff_split(self):
        user = User(email="test@exemple.fr")
        user.save()
        UserProfile.objects.create(user=user)
        b1 = Building.objects.create(
            rnb_id="1",
            status="constructed",
            event_type="creation",
            shape=GEOSGeometry("POLYGON((0 0, 0 0.5, 0.5 0.5, 0.5 0, 0 0))"),
        )
        Building.objects.create(rnb_id="t", event_type="creation")
        # reload the buildings to get the sys_period
        treshold = Building.objects.get(rnb_id="t").sys_period.lower

        created_buildings = b1.split(
            [
                {
                    "status": "constructed",
                    "addresses_cle_interop": [],
                    "shape": "POLYGON((0 0, 0 0.5, 0.5 0.5, 0.5 0, 0 0))",
                },
                {
                    "status": "constructed",
                    "addresses_cle_interop": [],
                    "shape": "POLYGON((0 0, 0 0.5, 0.5 0.5, 0.5 0, 0 0))",
                },
            ],
            user,
            {"source": "contribution"},
        )

        b2 = created_buildings[0]
        b3 = created_buildings[1]

        # we want all the diff since the creation of b1 (excluded)
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

        self.assertEqual(rows[0][0], "deactivate")
        self.assertEqual(rows[0][1], b1.rnb_id)
        self.assertEqual(rows[0][2], "constructed")

        self.assertEqual(rows[1][0], "create")
        self.assertEqual(rows[1][1], b2.rnb_id)
        self.assertEqual(rows[1][2], "constructed")

        self.assertEqual(rows[2][0], "create")
        self.assertEqual(rows[2][1], b3.rnb_id)
        self.assertEqual(rows[2][2], "constructed")

        # additional check: set a since date in the past to make sure the loop on the datetimes is working correctly
        # because rows of diff are fetched one day at a time
        treshold = treshold - datetime.timedelta(days=10)
        params = urlencode({"since": treshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)
        diff_text = get_content_from_streaming_response(r)
        reader = csv.reader(io.StringIO(diff_text), strict=True, delimiter=",")
        _headers = next(reader)
        rows = list(reader)
        self.assertEqual(len(rows), 5)

    def test_diff_no_since(self):
        # we want all the diff since the the creation of b1 (excluded)
        url = f"/api/alpha/buildings/diff/"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)

    def test_since_is_too_old(self):
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=210  # 7 months
        )
        params = urlencode({"since": since.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)

    def test_since_without_timezone(self):
        b = Building.objects.create(rnb_id="t", event_type="creation")
        threshold = Building.objects.get(rnb_id="t").sys_period.lower

        user = User.objects.get(username="marcella")
        b.update(
            status="constructed",
            user=user,
            event_origin={"source": "test"},
            addresses_id=[],
        )

        params = urlencode({"since": threshold.strftime("%Y-%m-%dT%H:%M:%S")})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_since_only_date(self):
        b = Building.objects.create(rnb_id="t", event_type="creation")
        threshold = Building.objects.get(rnb_id="t").sys_period.lower

        user = User.objects.get(username="marcella")
        b.update(
            status="constructed",
            user=user,
            event_origin={"source": "test"},
            addresses_id=[],
        )

        params = urlencode({"since": threshold.strftime("%Y-%m-%d")})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_since_is_invalid(self):
        url = f"/api/alpha/buildings/diff/?since=invalid"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 400)

    def test_diff_reactivation(self):
        user = User.objects.get(username="marcella")

        b1 = Building.objects.create(
            rnb_id="1",
            ext_ids=[
                {
                    "source": "test",
                    "source_version": "11_2024",
                    "id": "1",
                    "created_at": "2024-08-05T00:00:00Z",
                }
            ],
            addresses_id=["ADDRESS_ID_1"],
            status="constructed",
            event_type="creation",
        )

        threshold = Building.objects.get(rnb_id="1").sys_period.lower

        b1.deactivate(user=user, event_origin={"source": "contribution"})
        b1.reactivate(user=user, event_origin={"source": "contribution"})

        params = urlencode({"since": threshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"

        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)

        diff_text = get_content_from_streaming_response(r)
        reader = csv.DictReader(io.StringIO(diff_text))
        rows = list(reader)

        self.assertEqual(len(rows), 2)

        self.assertEqual(rows[0]["action"], "deactivate")
        self.assertEqual(rows[0]["rnb_id"], b1.rnb_id)
        self.assertEqual(rows[0]["status"], "constructed")
        self.assertEqual(rows[0]["is_active"], "0")
        self.assertEqual(rows[0]["event_type"], "deactivation")
        self.assertListEqual(json.loads(rows[0]["addresses_id"]), ["ADDRESS_ID_1"])

        self.assertEqual(rows[1]["action"], "reactivate")
        self.assertEqual(rows[1]["rnb_id"], b1.rnb_id)
        self.assertEqual(rows[1]["status"], "constructed")
        self.assertEqual(rows[1]["is_active"], "1")
        self.assertEqual(rows[1]["event_type"], "reactivation")
        self.assertListEqual(json.loads(rows[1]["addresses_id"]), ["ADDRESS_ID_1"])


class DiffInseeCodeTest(TransactionTestCase):
    def setUp(self):
        # User and organization
        user = User.objects.create_user(
            first_name="Test", last_name="User", username="testuser"
        )
        UserProfile.objects.create(user=user)
        org = Organization.objects.create(name="Test Org")
        org.users.add(user)

        # City with geometry (Paris area for testing)
        self.city_shape = GEOSGeometry(
            "MULTIPOLYGON(((2.3 48.8, 2.4 48.8, 2.4 48.9, 2.3 48.9, 2.3 48.8)))",
            srid=4326,
        )
        City.objects.create(code_insee="75056", name="Paris", shape=self.city_shape)

        # City without geometry (for error test)
        City.objects.create(code_insee="99998", name="Ville sans geom", shape=None)

    def test_diff_with_valid_insee_code(self):
        # Building inside Paris
        geom_inside = GEOSGeometry(
            "MULTIPOLYGON(((2.35 48.85, 2.36 48.85, 2.36 48.86, 2.35 48.86, 2.35 48.85)))",
            srid=4326,
        )
        b1 = Building.objects.create(
            rnb_id="INSIDE1",
            shape=geom_inside,
            point=geom_inside.point_on_surface,
            status="constructed",
            event_type="creation",
        )
        threshold = Building.objects.get(rnb_id="INSIDE1").sys_period.lower

        params = urlencode({"since": threshold.isoformat(), "insee_code": "75056"})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)

        # Check filename contains insee_code
        self.assertIn("diff_75056_", r["Content-Disposition"])

    def test_diff_with_unknown_insee_code(self):
        Building.objects.create(rnb_id="B1", event_type="creation")
        threshold = Building.objects.get(rnb_id="B1").sys_period.lower

        params = urlencode({"since": threshold.isoformat(), "insee_code": "99999"})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 404)
        self.assertIn("99999", r.content.decode())

    def test_diff_without_insee_code_unchanged(self):
        Building.objects.create(rnb_id="B1", event_type="creation")
        threshold = Building.objects.get(rnb_id="B1").sys_period.lower

        params = urlencode({"since": threshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        # Filename should not contain insee code
        self.assertNotIn("75056", r["Content-Disposition"])

    def test_diff_building_inside_city_included(self):
        # Building inside Paris
        geom_inside = GEOSGeometry(
            "MULTIPOLYGON(((2.35 48.85, 2.36 48.85, 2.36 48.86, 2.35 48.86, 2.35 48.85)))",
            srid=4326,
        )
        Building.objects.create(
            rnb_id="INSIDE",
            shape=geom_inside,
            point=geom_inside.point_on_surface,
            status="constructed",
            event_type="creation",
        )
        threshold = Building.objects.get(rnb_id="INSIDE").sys_period.lower

        user = User.objects.get(username="testuser")
        b = Building.objects.get(rnb_id="INSIDE")
        b.update(
            status="demolished",
            user=user,
            event_origin={"source": "test"},
            addresses_id=[],
        )

        params = urlencode({"since": threshold.isoformat(), "insee_code": "75056"})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        diff_text = get_content_from_streaming_response(r)
        reader = csv.DictReader(io.StringIO(diff_text))
        rows = list(reader)

        rnb_ids = [row["rnb_id"] for row in rows]
        self.assertIn("INSIDE", rnb_ids)

    def test_diff_building_outside_city_excluded(self):
        # Building inside Paris
        geom_inside = GEOSGeometry(
            "MULTIPOLYGON(((2.35 48.85, 2.36 48.85, 2.36 48.86, 2.35 48.86, 2.35 48.85)))",
            srid=4326,
        )
        Building.objects.create(
            rnb_id="INSIDE",
            shape=geom_inside,
            point=geom_inside.point_on_surface,
            status="constructed",
            event_type="creation",
        )

        # Building outside Paris (far away)
        geom_outside = GEOSGeometry(
            "MULTIPOLYGON(((0.1 45.1, 0.2 45.1, 0.2 45.2, 0.1 45.2, 0.1 45.1)))",
            srid=4326,
        )
        Building.objects.create(
            rnb_id="OUTSIDE",
            shape=geom_outside,
            point=geom_outside.point_on_surface,
            status="constructed",
            event_type="creation",
        )

        threshold = Building.objects.get(rnb_id="INSIDE").sys_period.lower

        user = User.objects.get(username="testuser")
        for rnb_id in ["INSIDE", "OUTSIDE"]:
            b = Building.objects.get(rnb_id=rnb_id)
            b.update(
                status="demolished",
                user=user,
                event_origin={"source": "test"},
                addresses_id=[],
            )

        params = urlencode({"since": threshold.isoformat(), "insee_code": "75056"})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        diff_text = get_content_from_streaming_response(r)
        reader = csv.DictReader(io.StringIO(diff_text))
        rows = list(reader)

        rnb_ids = [row["rnb_id"] for row in rows]
        self.assertIn("INSIDE", rnb_ids)
        self.assertNotIn("OUTSIDE", rnb_ids)

    def test_diff_building_overlapping_city_included(self):
        # Building that overlaps the city boundary
        geom_overlap = GEOSGeometry(
            "MULTIPOLYGON(((2.39 48.85, 2.42 48.85, 2.42 48.86, 2.39 48.86, 2.39 48.85)))",
            srid=4326,
        )
        Building.objects.create(
            rnb_id="OVERLAP",
            shape=geom_overlap,
            point=geom_overlap.point_on_surface,
            status="constructed",
            event_type="creation",
        )
        threshold = Building.objects.get(rnb_id="OVERLAP").sys_period.lower

        user = User.objects.get(username="testuser")
        b = Building.objects.get(rnb_id="OVERLAP")
        b.update(
            status="demolished",
            user=user,
            event_origin={"source": "test"},
            addresses_id=[],
        )

        params = urlencode({"since": threshold.isoformat(), "insee_code": "75056"})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        diff_text = get_content_from_streaming_response(r)
        reader = csv.DictReader(io.StringIO(diff_text))
        rows = list(reader)

        rnb_ids = [row["rnb_id"] for row in rows]
        self.assertIn("OVERLAP", rnb_ids)

    def test_diff_filename_with_insee_code(self):
        geom = GEOSGeometry(
            "MULTIPOLYGON(((2.35 48.85, 2.36 48.85, 2.36 48.86, 2.35 48.86, 2.35 48.85)))",
            srid=4326,
        )
        Building.objects.create(
            rnb_id="B1",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
            event_type="creation",
        )
        threshold = Building.objects.get(rnb_id="B1").sys_period.lower

        params = urlencode({"since": threshold.isoformat(), "insee_code": "75056"})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        self.assertRegex(
            r["Content-Disposition"],
            r'attachment; filename="diff_75056_.*\.csv"',
        )

    def test_diff_filename_without_insee_code(self):
        Building.objects.create(rnb_id="B1", event_type="creation")
        threshold = Building.objects.get(rnb_id="B1").sys_period.lower

        params = urlencode({"since": threshold.isoformat()})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        # Should match diff_{since}_{most_recent}.csv (no insee code)
        self.assertRegex(
            r["Content-Disposition"],
            r'attachment; filename="diff_\d{4}-.*\.csv"',
        )
        self.assertNotIn("75056", r["Content-Disposition"])

    def test_diff_city_with_null_shape(self):
        Building.objects.create(rnb_id="B1", event_type="creation")
        threshold = Building.objects.get(rnb_id="B1").sys_period.lower

        params = urlencode({"since": threshold.isoformat(), "insee_code": "99998"})
        url = f"/api/alpha/buildings/diff/?{params}"
        r = self.client.get(url)

        self.assertEqual(r.status_code, 500)
        self.assertIn("99998", r.content.decode())
