from django.test import TestCase

from batid.models import Building, BuildingWithHistory, BuildingHistoryOnly
from batid.services.data_fix.fill_empty_event_id import fill_empty_event_id


class TestMissingEventId(TestCase):

    def setUp(self):

        # The building to fill

        b = Building.objects.create(
            rnb_id="one",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_type="creation",
            event_id=None,  # Missing event_id
        )

        b.event_type = "update"
        b.status = "demolished"
        b.save()

        # Two buildings with merge and split event_type
        # They must not be fixed by the fill_empty_event_id function
        # Merge and split are more complex operations concerning multiple buildings
        # All those buildings should have the same event_id
        # The fill_empty_event_id function handles buildings one by one

        Building.objects.create(
            rnb_id="merge",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_type="merge",
            event_id=None,  # Missing event_id
        )

        Building.objects.create(
            rnb_id="split",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_type="merge",
            event_id=None,  # Missing event_id
        )

    def test_missing_event_id(self):

        # Verify some values before the fix
        versions_count = BuildingWithHistory.objects.all().count()
        self.assertEqual(versions_count, 4)

        past_version = BuildingHistoryOnly.objects.get(rnb_id="one")
        self.assertIsNone(past_version.event_id)
        old_updated_at = past_version.updated_at

        # ###### Trigger the fix ######
        # Correct the missing event_ids
        fill_empty_event_id()

        # The history trigger should have been disabled. The total number of versions should remain the same
        versions_count = BuildingWithHistory.objects.all().count()
        self.assertEqual(versions_count, 4)

        # The past version should now have an event_id
        past_version = BuildingHistoryOnly.objects.get(rnb_id="one")
        self.assertIsNotNone(past_version.event_id)

        # We want the updated_at value to remain unchanged despite the auto_now=True field setting
        new_updated_at = past_version.updated_at
        self.assertEqual(old_updated_at, new_updated_at)

        # The merge and split buildings should not have been modified
        merge_building = Building.objects.get(rnb_id="merge")
        self.assertIsNone(merge_building.event_id)
        split_building = Building.objects.get(rnb_id="split")
        self.assertIsNone(split_building.event_id)
