from batid.models import Building, BuildingHistoryOnly, BuildingWithHistory
from django.contrib.auth.models import User
from django.db import connection
from django.db.utils import InternalError
from django.test import TransactionTestCase


class TemporalTableCase(TransactionTestCase):
    def test_update_building(self):
        user = User.objects.create_user("alice", email="alice@example.com")
        building = Building.objects.create(rnb_id="XYZ")
        # We now update the building (and so create a new version of it)
        building.parent_buildings = [1]
        building.validated_by = [user.id]
        building.save()

        building.refresh_from_db()
        self.assertEqual(building.parent_buildings, [1])
        self.assertEqual(building.validated_by, [user.id])

        building_versions = BuildingWithHistory.objects.filter(rnb_id="XYZ")
        # the actual value is present, but also the previous one
        self.assertEqual(len(building_versions), 2)

        # if the sys_period upper bound is not null, it means the row is the historicized one
        previous_building_version = BuildingWithHistory.objects.filter(
            sys_period__endswith__isnull=False
        ).all()
        self.assertEqual(len(previous_building_version), 1)
        self.assertEqual(previous_building_version[0].parent_buildings, None)
        self.assertEqual(previous_building_version[0].validated_by, [])

        current_building_version = BuildingWithHistory.objects.filter(
            sys_period__endswith__isnull=True
        )
        self.assertEqual(len(current_building_version), 1)
        self.assertEqual(current_building_version[0].parent_buildings, [1])
        self.assertEqual(current_building_version[0].validated_by, [user.id])

        building_history_only = BuildingHistoryOnly.objects.all()
        self.assertEqual(len(building_history_only), 1)
        self.assertEqual(building_history_only[0].validated_by, [])

        # save the building a second time to make sure the validated_by
        # value carried over to history is not always the default empty list
        other_user = User.objects.create_user("bob", email="bob@example.com")
        building.validated_by = [user.id, other_user.id]
        building.save()

        building.refresh_from_db()
        self.assertEqual(building.validated_by, [user.id, other_user.id])

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
        self.assertEqual(latest_historicized.validated_by, [user.id])

        current = BuildingWithHistory.objects.get(
            rnb_id="XYZ", sys_period__endswith__isnull=True
        )
        self.assertEqual(current.validated_by, [user.id, other_user.id])

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
