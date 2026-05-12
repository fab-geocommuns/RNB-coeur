from batid.models import Building, BuildingHistoryOnly, BuildingWithHistory
from django.contrib.auth.models import User
from django.test import TestCase


class TemporalTableCase(TestCase):
    def test_update_building(self):
        user = User.objects.create_user("alice", email="alice@example.com")
        building = Building.objects.create(rnb_id="XYZ")
        # We now update the building (and so create a new version of it)
        building.parent_buildings = [1]
        building.marked_as_correct_by = [user.id]
        building.save()

        building.refresh_from_db()
        self.assertEqual(building.parent_buildings, [1])
        self.assertEqual(building.marked_as_correct_by, [user.id])

        building_versions = BuildingWithHistory.objects.filter(rnb_id="XYZ")
        # the actual value is present, but also the previous one
        self.assertEqual(len(building_versions), 2)

        # if the sys_period upper bound is not null, it means the row is the historicized one
        previous_building_version = BuildingWithHistory.objects.filter(
            sys_period__endswith__isnull=False
        ).all()
        self.assertEqual(len(previous_building_version), 1)
        self.assertEqual(previous_building_version[0].parent_buildings, None)
        self.assertEqual(previous_building_version[0].marked_as_correct_by, [])

        current_building_version = BuildingWithHistory.objects.filter(
            sys_period__endswith__isnull=True
        )
        self.assertEqual(len(current_building_version), 1)
        self.assertEqual(current_building_version[0].parent_buildings, [1])
        self.assertEqual(current_building_version[0].marked_as_correct_by, [user.id])

        building_history_only = BuildingHistoryOnly.objects.all()
        self.assertEqual(len(building_history_only), 1)
        self.assertEqual(building_history_only[0].marked_as_correct_by, [])

        # save the building a second time to make sure the marked_as_correct_by
        # value carried over to history is not always the default empty list
        other_user = User.objects.create_user("bob", email="bob@example.com")
        building.marked_as_correct_by = [user.id, other_user.id]
        building.save()

        building.refresh_from_db()
        self.assertEqual(building.marked_as_correct_by, [user.id, other_user.id])

        # there are now three versions: two historicized + the current one
        self.assertEqual(BuildingWithHistory.objects.filter(rnb_id="XYZ").count(), 3)

        # the latest historicized version should hold the value just before this
        # second save, which is [user.id] — not the default empty list
        latest_historicized = (
            BuildingWithHistory.objects.filter(
                rnb_id="XYZ", sys_period__endswith__isnull=False
            )
            .order_by("-sys_period")
            .first()
        )
        self.assertEqual(latest_historicized.marked_as_correct_by, [user.id])

        current = BuildingWithHistory.objects.get(
            rnb_id="XYZ", sys_period__endswith__isnull=True
        )
        self.assertEqual(current.marked_as_correct_by, [user.id, other_user.id])

    def test_delete_building(self):
        # we check that the temporal table works properly, even if deleting a building like that is NEVER expected.
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
