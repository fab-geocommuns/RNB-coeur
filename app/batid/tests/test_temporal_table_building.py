from django.test import TestCase

from batid.models import Building
from batid.models import BuildingHistoryOnly
from batid.models import BuildingWithHistory


class TemporalTableCase(TestCase):
    def test_update_building(self):
        building = Building.objects.create(rnb_id="XYZ")
        # We now update the building (and so create a new version of it)
        building.parent_buildings = [1]
        building.save()

        building.refresh_from_db()
        self.assertEqual(building.parent_buildings, [1])

        building_versions = BuildingWithHistory.objects.filter(rnb_id="XYZ")
        # the actual value is present, but also the previous one
        self.assertEqual(len(building_versions), 2)

        # if the sys_period upper bound is not null, it means the row is the historicized one
        previous_building_version = BuildingWithHistory.objects.filter(
            sys_period__endswith__isnull=False
        ).all()
        self.assertEqual(len(previous_building_version), 1)
        self.assertEqual(previous_building_version[0].parent_buildings, None)

        current_building_version = BuildingWithHistory.objects.filter(
            sys_period__endswith__isnull=True
        )
        self.assertEqual(len(current_building_version), 1)
        self.assertEqual(current_building_version[0].parent_buildings, [1])

        building_history_only = BuildingHistoryOnly.objects.all()
        self.assertEqual(len(building_history_only), 1)

    def test_delete_building(self):
        building = Building.objects.create(rnb_id="XYZ")
        building.delete()

        buildings = Building.objects.all()
        # check the building has been deleted
        self.assertEqual(len(buildings), 0)

        building_history = BuildingWithHistory.objects.filter(rnb_id="XYZ")
        # yala, the building is still accessible in the history table
        self.assertEqual(len(building_history), 1)

    def test_history_is_read_only(self):
        # trying to manually insert a new row in the history table should raise an exception
        # this table is not supposed to be written only with triggers
        self.assertRaises(Exception, BuildingWithHistory.objects.create, rnb_id="XYZ")
        self.assertRaises(Exception, BuildingHistoryOnly.objects.create, rnb_id="XYZ")
