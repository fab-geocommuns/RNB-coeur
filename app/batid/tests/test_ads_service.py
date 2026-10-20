from batid.models import ADS, BuildingADS
from batid.services import ads
from batid.services.ads import get_cities
from batid.tests.helpers import (
    create_bdg,
    create_default_bdg,
    create_grenoble,
    create_paris,
)
from django.contrib.auth.models import User
from django.test import TestCase

PARIS_COORDS = [
    [2.349804906833981, 48.85789205519228],
    [2.349701279442314, 48.85786369735885],
    [2.3496535925009994, 48.85777922711969],
    [2.349861764341199, 48.85773095834841],
    [2.3499452164882086, 48.857847406681174],
    [2.349804906833981, 48.85789205519228],
]


class TestGetCities(TestCase):
    def test_cities_from_rnb_ids(self):
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


class TestExportFormat(TestCase):
    def test_ads_export(self):
        """
        Input: one ADS with one building operation.
        Expected: one dict with the file number, rnb_id, shape and username.
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
