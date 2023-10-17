from django.contrib.gis.geos import Point
from django.test import TestCase
from batid.models import Building, Address
from batid.services.search_bdg import BuildingGuess
from django.test import tag
from unittest.mock import patch

from batid.tests.helpers import (
    mock_ban_geocoder_result,
    mock_photon_geocoder_empty_result,
)


class TestSearch(TestCase):
    fixtures = ["village.json"]

    def test_search(self):
        assert len(Building.objects.all()) == 137

    def test_on_bdg(self):
        # Simple test with a point on the building

        point = Point(5.7359531, 45.1799726, srid=4326)

        search = BuildingGuess()
        search.set_params(point=point)

        best = search.get_queryset()[0]

        self.assertEqual(best.rnb_id, "CS1RPEWZNNEW")

    def test_on_edge_bdg(self):
        # Test a point on a building edge close to another contiguous building

        point = Point(5.73571756, 45.17993763, srid=4326)

        search = BuildingGuess()
        search.set_params(point=point)

        best = search.get_queryset()[0]

        self.assertEqual(best.rnb_id, "XTNU9H8DASX6")

    def test_point_very_far_from_village(self):
        point = Point(5.726823, 45.185496, srid=4326)

        search = BuildingGuess()
        search.set_params(point=point)
        results = search.get_queryset()

        self.assertEqual(len(results), 0)

    @patch("batid.services.geocoders.BanGeocoder.geocode")
    @patch("batid.services.geocoders.PhotonGeocoder.geocode")
    def test_simple_address_search(self, photon_geocode, ban_geocode):
        ban_geocode.return_value = mock_ban_geocoder_result(
            id="38185_6400_00003", lng=5.736469, lat=45.179156
        )
        photon_geocode.return_value = mock_photon_geocoder_empty_result()

        address = "3  impasse simard, Grenoble"

        search = BuildingGuess()
        search.set_params(address=address)

        results = search.get_queryset()

        # Test geocoders
        ban_geocode.assert_called_once()

        self.assertEqual(results[0].rnb_id, "78AEVARTSXL6")

    @tag("futuristic_search")
    def test_futuristic_search(self):
        search = BuildingGuess()
        # I give no search params
        search.set_params()
        results = search.get_queryset()
        # the correct result is given!
        self.assertEqual(len(results), 1)
