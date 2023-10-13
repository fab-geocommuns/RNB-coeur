import json
from datetime import datetime

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase

from batid.models import Building, BuildingStatus
from batid.tests.helpers import create_default_bdg


class StatusTestCase(TestCase):
    def setUp(self):
        # One building with one status
        b = create_default_bdg(rnb_id="WITH-STATUS")

        happened_at = datetime(1975, 1, 1)
        BuildingStatus.objects.create(
            building=b,
            type=BuildingStatus.CONSTRUCTION_PROJECT,
            happened_at=happened_at,
            is_current=True,
        )

    def test_current_status(self):
        b = Building.objects.get(rnb_id="WITH-STATUS")
        self.assertEqual(b.current_status.type, BuildingStatus.CONSTRUCTION_PROJECT)

    def test_current_replacement(self):
        b = create_default_bdg(rnb_id="TWO-STATUS")

        happened_at = datetime(1975, 1, 1)
        old_s = BuildingStatus.objects.create(
            building=b,
            type=BuildingStatus.CONSTRUCTION_PROJECT,
            happened_at=happened_at,
            is_current=True,
        )

        happened_at = datetime(1980, 1, 1)
        BuildingStatus.objects.create(
            building=b,
            type=BuildingStatus.CONSTRUCTED,
            happened_at=happened_at,
            is_current=True,
        )

        # The current status should be the most recent one, tagged with current
        self.assertEqual(b.current_status.type, BuildingStatus.CONSTRUCTED)

        # Reload the old status
        old_s.refresh_from_db()
        self.assertEqual(old_s.is_current, False)

    def test_status_order(self):
        b = create_default_bdg(rnb_id="FOUR-STATUS")

        # Create the middle status
        happened_at = datetime(1980, 1, 1)
        BuildingStatus.objects.create(
            building=b,
            type=BuildingStatus.CONSTRUCTED,
            happened_at=happened_at,
            is_current=False,
        )

        # Create the newest status
        happened_at = datetime(2020, 1, 1)
        BuildingStatus.objects.create(
            building=b,
            type=BuildingStatus.DEMOLISHED,
            happened_at=happened_at,
            is_current=True,
        )

        # Create the olest status (no happened_at)
        BuildingStatus.objects.create(
            building=b,
            type=BuildingStatus.CONSTRUCTION_PROJECT,
            is_current=False,
        )

        b.refresh_from_db()

        status = b.status.all()
        self.assertEqual(status[0].type, BuildingStatus.CONSTRUCTION_PROJECT)
        self.assertEqual(status[1].type, BuildingStatus.CONSTRUCTED)
        self.assertEqual(status[2].type, BuildingStatus.DEMOLISHED)

    def test_missing_status(self):
        b = create_default_bdg(rnb_id="MISSING-S")
        BuildingStatus.objects.create(
            building=b,
            type=BuildingStatus.DEMOLISHED,
            happened_at=datetime(2020, 1, 1),
            is_current=True,
        )

        b.refresh_from_db()

        # Assert the current status is the right one
        self.assertEqual(b.current_status.type, BuildingStatus.DEMOLISHED)

        # Assert the missing status is created
        self.assertEqual(b.status.count(), 2)
        self.assertEqual(b.status.first().type, BuildingStatus.CONSTRUCTED)
        self.assertEqual(b.status.first().is_current, False)
