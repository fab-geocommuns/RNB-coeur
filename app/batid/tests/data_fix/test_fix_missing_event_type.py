from datetime import timedelta
from django.utils import timezone

from django.test import TransactionTestCase, TestCase

from batid.services.data_fix.fill_empty_event_type import _fetch, fill_empty_event_type
from batid.models import Building
from batid.models import BuildingHistoryOnly


class TestFix(TestCase):

    def setUp(self):

        # One with empty Building and BuildingHistoryOnly
        b = Building.objects.create(
            rnb_id="one",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_type=None,  # Missing event_type
        )

        b.status = "demolished"
        b.save()

        # Another one with event_type filled
        b = Building.objects.create(
            rnb_id="two",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_type="creation",  # Filled event_type
        )

        b.shape = "POINT(2 2)"
        b.event_type = "update"
        b.save()

    def test_fetch(self):

        rows = _fetch(10)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].event_type)
        self.assertIsInstance(rows[0], BuildingHistoryOnly)

    def test_fix(self):

        updated_rows = fill_empty_event_type(10)

        self.assertEqual(updated_rows, 1)

        row = BuildingHistoryOnly.objects.get(rnb_id="one")
        self.assertEqual(row.event_type, "creation")


class TestFixCreationOnly(TestCase):

    def setUp(self):

        # We will create two history rows with event_type=None
        # One will be creation (created_at - lower(sys_period) < 2 seconds )
        # The other will be update (created_at - lower(sys_period) > 2 seconds)
        # The first one should be fixed, the second one should not

        # The building to fill/fix
        b = Building.objects.create(
            rnb_id="three",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_type=None,  # Missing event_type
        )

        b.status = "demolished"
        b.save()

        # The building to "old" to be fixed
        old_b = Building.objects.create(
            rnb_id="three_old",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_type=None,  # Missing event_type
        )

        old_b.status = "demolished"
        old_b.save()

        # We now have two versionsof the building.
        # We artifically set the created_at to be older than 2 seconds

        old_creation_row = BuildingHistoryOnly.objects.get(rnb_id="three_old")

        old_creation_row.created_at = old_creation_row.sys_period.lower + timedelta(
            seconds=3
        )
        old_creation_row.save()

    def test_fix_creation_only(self):

        all_history_rows = BuildingHistoryOnly.objects.all()
        self.assertEqual(len(all_history_rows), 2)

        updated_rows = fill_empty_event_type(10)

        self.assertEqual(updated_rows, 1)

        old_creation_row = BuildingHistoryOnly.objects.get(rnb_id="three_old")
        self.assertIsNone(old_creation_row.event_type)


class TestBatchSize(TestCase):

    def setUp(self):

        b = Building.objects.create(
            rnb_id="batch_test",
            status="constructed",
            shape="POINT(1 1)",
            is_active=True,
            event_type=None,  # Missing event_type
        )

        b.status = "demolished"
        b.save()

        b = Building.objects.create(
            rnb_id="batch_test_2",
            status="constructed",
            shape="POINT(2 2)",
            is_active=True,
            event_type=None,  # Missing event_type
        )
        b.status = "demolished"
        b.save()

    def test_batch_size(self):

        updated_rows = fill_empty_event_type(batch_size=1)
        self.assertEqual(updated_rows, 1)
