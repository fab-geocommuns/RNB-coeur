# Thoses were used only during the development and execution of the fill_event_id fix
# They cannot be used in normal situation since they require to disable the write protection set in dbrouters.py


# from django.test import TransactionTestCase

# from batid.models import Building
# from batid.models import BuildingHistoryOnly
# from batid.models import BuildingWithHistory
# from batid.services.data_fix.fill_empty_event_id import fill_empty_event_id


# class TestMissingEventId(TransactionTestCase):
#     def setUp(self):

#         # The building to fill

#         b = Building.objects.create(
#             rnb_id="one",
#             status="constructed",
#             shape="POINT(1 1)",
#             is_active=True,
#             event_type="creation",
#             event_id=None,  # Missing event_id
#         )

#         b.event_type = "update"
#         b.status = "demolished"
#         b.save()

#         # Two buildings with merge and split event_type
#         # They must not be fixed by the fill_empty_event_id function
#         # Merge and split are more complex operations concerning multiple buildings
#         # All those buildings should have the same event_id
#         # The fill_empty_event_id function handles buildings one by one

#         Building.objects.create(
#             rnb_id="merge",
#             status="constructed",
#             shape="POINT(1 1)",
#             is_active=True,
#             event_type="merge",
#             event_id=None,  # Missing event_id
#         )

#         Building.objects.create(
#             rnb_id="split",
#             status="constructed",
#             shape="POINT(1 1)",
#             is_active=True,
#             event_type="merge",
#             event_id=None,  # Missing event_id
#         )

#     def test_missing_event_id(self):

#         # Verify some values before the fix
#         versions_count = BuildingWithHistory.objects.all().count()
#         self.assertEqual(versions_count, 4)

#         history_row = BuildingHistoryOnly.objects.get(rnb_id="one")
#         self.assertIsNone(history_row.event_id)
#         history_old_updated_at = history_row.updated_at

#         current_row = Building.objects.get(rnb_id="one")
#         self.assertIsNone(current_row.event_id)
#         current_old_updated_at = current_row.updated_at

#         # ###### Trigger the fix ######
#         # Correct the missing event_ids
#         updated_rows = fill_empty_event_id()
#         self.assertEqual(updated_rows, 2)

#         # The history trigger should have been disabled. The total number of versions should remain the same
#         versions_count = BuildingWithHistory.objects.all().count()
#         self.assertEqual(versions_count, 4)

#         # ##### Check history row #####

#         # The past version should now have an event_id
#         history_row.refresh_from_db()
#         self.assertIsNotNone(history_row.event_id)

#         # We want the updated_at value to remain unchanged despite the auto_now=True field setting
#         history_new_updated_at = history_row.updated_at
#         self.assertEqual(history_old_updated_at, history_new_updated_at)

#         # ##### Check current row #####

#         # The current version should now have an event_id
#         current_row.refresh_from_db()
#         self.assertIsNotNone(current_row.event_id)

#         # We want the updated_at value to remain unchanged despite the auto_now=True field setting
#         current_new_updated_at = current_row.updated_at
#         self.assertEqual(current_old_updated_at, current_new_updated_at)

#         # ##### Other checks #####

#         # The merge and split buildings should not have been modified
#         merge_building = Building.objects.get(rnb_id="merge")
#         self.assertIsNone(merge_building.event_id)
#         split_building = Building.objects.get(rnb_id="split")
#         self.assertIsNone(split_building.event_id)

#         # Check the trigger is restored
#         current_row.status = "constructed"
#         current_row.save()

#         bdg_one_rows = BuildingWithHistory.objects.filter(rnb_id="one")
#         self.assertEqual(len(bdg_one_rows), 3)

#     def test_batch_size(self):

#         history_row = BuildingHistoryOnly.objects.get(rnb_id="one")
#         self.assertIsNone(history_row.event_id)

#         current_row = Building.objects.get(rnb_id="one")
#         self.assertIsNone(current_row.event_id)

#         updated_rows = fill_empty_event_id(batch_size=1)
#         self.assertEqual(updated_rows, 1)

#         # We updated only one row
#         # The script starts with the history rows
#         # So the history row should have an event_id now
#         history_row.refresh_from_db()
#         self.assertIsNotNone(history_row.event_id)

#         # The current row should still have no event_id
#         # since the batch size was 1
#         current_row.refresh_from_db()
#         self.assertIsNone(current_row.event_id)
