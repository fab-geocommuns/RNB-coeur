from django.contrib.gis.geos import Point
from django.test import TestCase
from batid.models import Building, Address
from batid.services.search_bdg import BuildingSearch
from django.test import tag


# loads the village fixture in the database
# useful from a jupyter notebook
def create_village():
    from django.core.management import call_command

    call_command("loaddata", "village.json", verbosity=0, app_label="batid")


class TestSearch(TestCase):
    fixtures = ["village.json"]

    def test_search(self):
        assert len(Building.objects.all()) == 137

    def test_on_bdg(self):
        # Simple test with a point on the building

        point = Point(5.7359531, 45.1799726, srid=4326)

        search = BuildingSearch()
        search.set_params(point=point)

        best = search.get_queryset()[0]

        self.assertEqual(best.rnb_id, "CS1RPEWZNNEW")

    def test_on_edge_bdg(self):
        # Test a point on a building edge close to another contiguous building

        point = Point(5.73571756, 45.17993763, srid=4326)

        search = BuildingSearch()
        search.set_params(point=point)

        best = search.get_queryset()[0]

        self.assertEqual(best.rnb_id, "XTNU9H8DASX6")

    def test_point_very_far_from_village(self):
        point = Point(5.726823, 45.185496, srid=4326)

        search = BuildingSearch()
        search.set_params(point=point)
        results = search.get_queryset()

        self.assertEqual(len(results), 0)

    @tag("futuristic_search")
    def test_futuristic_search(self):
        search = BuildingSearch()
        # I give no search params
        search.set_params()
        results = search.get_queryset()
        # the correct result is given!
        self.assertEqual(len(results), 1)
