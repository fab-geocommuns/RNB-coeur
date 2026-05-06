from batid.models import Building, BuildingHistoryOnly, BuildingWithHistory
from django.db import connection
from django.db.utils import InternalError
from django.test import TransactionTestCase


class TemporalTableCase(TransactionTestCase):
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
        # the temporal table would save the building as history before its deletion, but a deletion is just blocked by another trigger.
        building = Building.objects.create(rnb_id="XYZ")
        sql = "delete from batid_building where rnb_id = 'XYZ';"

        with self.assertRaises(InternalError):
            with connection.cursor() as cursor:
                cursor.execute(sql)

        buildings = Building.objects.all()
        # check the building has not been deleted
        self.assertEqual(len(buildings), 1)

        building_history = BuildingHistoryOnly.objects.filter(rnb_id="XYZ")
        # no history was created, because nothing was deleted
        self.assertEqual(len(building_history), 0)

    def test_history_is_read_only(self):
        # trying to manually insert a new row in the history table should raise an exception
        # this table is not supposed to be written only with triggers
        self.assertRaises(Exception, BuildingWithHistory.objects.create, rnb_id="XYZ")
        self.assertRaises(Exception, BuildingHistoryOnly.objects.create, rnb_id="XYZ")

    def test_delete_building_history_is_forbidden(self):
        """
        Input: a building is created and then updated, which produces a row in
        the batid_building_history table.
        Expected: deleting that history row is forbidden both via the Django
        ORM (raises NotImplementedError on the model's delete method) and via
        a raw SQL DELETE (blocked by the prevent_delete_building_history_trigger
        Postgres trigger), and the history row remains in the table.
        """
        building = Building.objects.create(rnb_id="XYZ")
        building.parent_buildings = [1]
        building.save()

        history_row = BuildingHistoryOnly.objects.get(rnb_id="XYZ")

        # ORM side: the model's delete() method must raise NotImplementedError
        with self.assertRaises(NotImplementedError):
            history_row.delete()

        # SQL side: the Postgres trigger must block the DELETE
        sql = "delete from batid_building_history where rnb_id = 'XYZ';"
        with self.assertRaises(InternalError):
            with connection.cursor() as cursor:
                cursor.execute(sql)

        # the history row is still there
        self.assertEqual(BuildingHistoryOnly.objects.filter(rnb_id="XYZ").count(), 1)
