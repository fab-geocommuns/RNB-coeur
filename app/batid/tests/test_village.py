from django.contrib.gis.geos import Point
from django.test import TestCase
from batid.models import Building, Address
from batid.services.guess_bdg import BuildingGuess
from django.test import tag
from unittest.mock import patch

from batid.tests.helpers import (
    mock_ban_geocoder_result,
    mock_photon_geocoder_empty_result,
)


class TestSearch(TestCase):
    fixtures = ["village.json", "village_plots.json"]

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

    @patch("batid.services.geocoders.BanGeocoder.geocode")
    @patch("batid.services.geocoders.PhotonGeocoder.geocode")
    def test_point_and_address(self, photon_geocode, ban_geocode):
        # We test a point and address.
        # The point is close to two buildings, the address should make the difference to find the right building

        ban_geocode.return_value = mock_ban_geocoder_result(
            id="38185_3240_00002", lng=5.735239, lat=45.17931700000001
        )
        photon_geocode.return_value = mock_photon_geocoder_empty_result()

        address = "2  rue germain, Grenoble"
        point = Point(5.73520463, 45.17937231, srid=4326)

        search = BuildingSearch()
        search.set_params(address=address, point=point)

        results = search.get_queryset()

        self.assertEqual(results[0].rnb_id, "8JAX6VVU378C")

    def test_on_this_road_side(self):
        # We test the "on this side of the road" filter on point query
        # We have a closer building (DK89W1B51UCH) than the expected one but on the wrong side of the road

        point = Point(5.736114236184472, 45.178655320207696, srid=4326)

        search = BuildingSearch()
        search.set_params(point=point)

        results = search.get_queryset()

        self.assertEqual(results[0].rnb_id, "GTRH2SQNY8G1")

    @tag("futuristic_search")
    def test_futuristic_search(self):
        search = BuildingGuess()
        # I give no search params
        search.set_params()
        results = search.get_queryset()
        # the correct result is given!
        self.assertEqual(len(results), 1)
