from django.test import TestCase

from batid.models import Building, BuildingWithHistory, BuildingHistoryOnly
from batid.services.data_fix.fill_empty_event_id import fill_empty_event_id


class TestMissingEventId(TestCase):

    def setUp(self):

        b = Building.objects.create(
            rnb_id="one",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_id=None,  # Missing event_id
        )

        b.status = "demolished"
        b.save()

    def test_missing_event_id(self):

        versions_count = BuildingWithHistory.objects.all().count()
        self.assertEqual(versions_count, 2)

        past_version = BuildingHistoryOnly.objects.get(rnb_id="one")
        self.assertIsNone(past_version.event_id)

        # Correct the missing event_ids
        fill_empty_event_id()

        versions_count = BuildingWithHistory.objects.all().count()
        self.assertEqual(versions_count, 2)

        past_version = BuildingHistoryOnly.objects.get(rnb_id="one")
        self.assertIsNotNone(past_version.event_id)
