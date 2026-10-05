"""Tests covering the raw SQL paths affected by the PostgreSQL driver swap (issue #998)."""

from batid.models import ADS, Building, BuildingADS, Candidate, Contribution
from batid.services import ads, contributions
from batid.services.ads import get_cities
from batid.services.candidate import Inspector
from batid.tests.helpers import (
    coords_to_mp_geom,
    create_bdg,
    create_default_bdg,
    create_grenoble,
    create_paris,
)
from django.contrib.auth.models import User
from django.test import TestCase
from freezegun import freeze_time
from rest_framework.test import APITestCase

PARIS_COORDS = [
    [2.349804906833981, 48.85789205519228],
    [2.349701279442314, 48.85786369735885],
    [2.3496535925009994, 48.85777922711969],
    [2.349861764341199, 48.85773095834841],
    [2.3499452164882086, 48.857847406681174],
    [2.349804906833981, 48.85789205519228],
]


class TestGetCitiesByRnbIds(TestCase):
    def test_rnb_ids_only(self):
        """
        Input: one building in Paris, one in Grenoble, one unknown rnb_id.
        Expected: both cities returned ordered by code_insee, one id works,
        empty inputs return [].
        """
        create_paris()
        create_grenoble()
        create_bdg("PARISBDG0001", PARIS_COORDS)
        create_default_bdg("GRENOBLEBDG1")

        cities = get_cities(["GRENOBLEBDG1", "PARISBDG0001", "UNKNOWN00000"], [])
        self.assertEqual([c.code_insee for c in cities], ["38185", "75056"])
        self.assertEqual(
            [c.code_insee for c in get_cities(["GRENOBLEBDG1"], [])], ["38185"]
        )
        self.assertEqual(get_cities([], []), [])


class TestGuessStatusFilter(APITestCase):
    @freeze_time("2025-01-01")
    def test_status_filter(self):
        """
        Input: a constructed and a demolished building at the same place, guess
        by point with status=constructed then constructed,demolished.
        Expected: first call returns the constructed one only, second both.
        """
        coords = [
            [5.721187072129851, 45.18439363812283],
            [5.721094925229238, 45.184330511384644],
            [5.721122483180295, 45.184274061453465],
            [5.721241326846666, 45.18428316628476],
            [5.721187072129851, 45.18439363812283],
        ]
        create_bdg("CONSTRUCTED1", coords)
        create_bdg("DEMOLISHED01", coords)
        Building.objects.filter(rnb_id="DEMOLISHED01").update(status="demolished")

        url = "/api/alpha/buildings/guess/?point=45.184327114924656,5.721176133001023"
        r = self.client.get(url + "&status=constructed")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([b["rnb_id"] for b in r.json()], ["CONSTRUCTED1"])

        r = self.client.get(url + "&status=constructed,demolished")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            sorted(b["rnb_id"] for b in r.json()), ["CONSTRUCTED1", "DEMOLISHED01"]
        )


class TestInspectorMatchingStatus(TestCase):
    def test_non_real_status_is_not_a_match(self):
        """
        Input: candidate overlapping a demolished and a constructed building.
        Expected: only the constructed building matches; the candidate shape is
        read back as a geometry (no EWKB bytes parsing error).
        """
        create_bdg("CONSTRUCTED1", PARIS_COORDS)
        create_bdg("DEMOLISHED01", PARIS_COORDS)
        Building.objects.filter(rnb_id="DEMOLISHED01").update(status="demolished")
        Candidate.objects.create(
            shape=coords_to_mp_geom(PARIS_COORDS),
            source="bdnb",
            source_version="7.2",
            source_id="bdnb_1",
            address_keys=[],
            is_light=False,
            created_by={"id": 46, "source": "import"},
        )

        inspector = Inspector()
        inspector.get_candidate()
        self.assertIsNotNone(inspector.candidate)
        self.assertEqual(inspector.candidate.shape.geom_type, "MultiPolygon")
        inspector.get_matching_bdgs()
        self.assertEqual([b.rnb_id for b in inspector.matching_bdgs], ["CONSTRUCTED1"])


class TestExportFormat(TestCase):
    def test_ads_and_contributions_export(self):
        """
        Input: one ADS with one building operation, one contribution.
        Expected: one dict per export with the file number, rnb_id, shape and username
        for the ADS, and the text for the contribution.
        """
        user = User.objects.create_user(username="exporter", email="e@example.com")
        ads_obj = ADS.objects.create(file_number="ADS-1", creator=user)
        BuildingADS.objects.create(
            ads=ads_obj,
            rnb_id="BDG000000001",
            operation="build",
            shape="POINT(2.35 48.85)",
        )
        rows = ads.export_format()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["file_number"], "ADS-1")
        self.assertEqual(rows[0]["rnb_id"], "BDG000000001")
        self.assertEqual(rows[0]["shape"], "POINT(2.35 48.85)")
        self.assertEqual(rows[0]["username"], "exporter")

        Contribution.objects.create(rnb_id="BDG000000001", text="hello", user=user)
        rows = contributions.export_format()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "hello")
