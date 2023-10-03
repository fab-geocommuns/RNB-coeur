from django.test import TestCase
from batid.models import Building, Address


# loads the village fixture in the database
# useful from a jupyter notebook
def create_village():
    from django.core.management import call_command

    call_command("loaddata", "village.json", verbosity=0, app_label="batid")


class TestSearch(TestCase):
    fixtures = ["village.json"]

    def test_search(self):
        assert len(Building.objects.all()) == 137
