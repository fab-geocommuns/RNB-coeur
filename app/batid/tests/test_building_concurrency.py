import threading

from batid.exceptions import OperationOnInactiveBuilding, RevertNotAllowed
from batid.models import Building, BuildingHistoryOnly
from batid.tests.factories.users import ContributorUserFactory
from django.contrib.gis.geos import GEOSGeometry
from django.db import connections
from django.test import TestCase, TransactionTestCase

EVENT_ORIGIN = {"source": "contribution", "contribution_id": 1}
SHAPE = "POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))"


class StaleInstanceTest(TestCase):
    """
    The RNB business functions (deactivate, reactivate, update) must check the
    building state as it is in the database, not as it was when the caller
    loaded its Python instance (issue #955). These tests load two instances of
    the same building, write through the first one and check the second one
    does not overwrite that write.
    """

    def setUp(self) -> None:
        self.user = ContributorUserFactory(username="bob")
        self.rnb_id = "XXXXYYYYZZZZ"
        Building.objects.create(rnb_id=self.rnb_id, shape=GEOSGeometry(SHAPE))

    def test_deactivate_on_stale_instance(self):
        """
        Input: two instances of the same active building; the first one is
        deactivated, then deactivate() is called on the second (stale) one.
        Expected: the second call raises OperationOnInactiveBuilding and the
        history holds no extra deactivation.
        """
        fresh = Building.objects.get(rnb_id=self.rnb_id)
        stale = Building.objects.get(rnb_id=self.rnb_id)

        fresh.deactivate(self.user, EVENT_ORIGIN)

        with self.assertRaises(OperationOnInactiveBuilding):
            stale.deactivate(self.user, EVENT_ORIGIN)

        building = Building.objects.get(rnb_id=self.rnb_id)
        self.assertFalse(building.is_active)
        self.assertEqual(building.event_id, fresh.event_id)
        self.assertEqual(
            BuildingHistoryOnly.objects.filter(
                rnb_id=self.rnb_id, event_type="deactivation"
            ).count(),
            0,
        )

    def test_reactivate_on_stale_instance(self):
        """
        Input: a deactivated building loaded in two instances; the first one
        is reactivated, then reactivate() is called on the second (stale) one.
        Expected: the second call raises RevertNotAllowed and the building
        keeps the event_id of the first reactivation.
        """
        Building.objects.get(rnb_id=self.rnb_id).deactivate(self.user, EVENT_ORIGIN)

        fresh = Building.objects.get(rnb_id=self.rnb_id)
        stale = Building.objects.get(rnb_id=self.rnb_id)

        fresh.reactivate(self.user, EVENT_ORIGIN)

        with self.assertRaises(RevertNotAllowed):
            stale.reactivate(self.user, EVENT_ORIGIN)

        building = Building.objects.get(rnb_id=self.rnb_id)
        self.assertTrue(building.is_active)
        self.assertEqual(building.event_id, fresh.event_id)

    def test_update_on_stale_instance(self):
        """
        Input: an active building loaded in two instances; the first one is
        deactivated, then update() is called on the second (stale) one.
        Expected: update() raises OperationOnInactiveBuilding and the building
        stays inactive (a stale update used to silently re-activate it, since
        it saved the whole instance including is_active=True).
        """
        fresh = Building.objects.get(rnb_id=self.rnb_id)
        stale = Building.objects.get(rnb_id=self.rnb_id)

        fresh.deactivate(self.user, EVENT_ORIGIN)

        with self.assertRaises(OperationOnInactiveBuilding):
            stale.update(
                self.user, EVENT_ORIGIN, status="demolished", addresses_id=None
            )

        building = Building.objects.get(rnb_id=self.rnb_id)
        self.assertFalse(building.is_active)
        self.assertEqual(building.event_type, "deactivation")


class ConcurrentDeactivationModelTest(TransactionTestCase):
    """
    Same race as ConcurrentDeactivationTest in api_alpha, but calling
    Building.deactivate() directly: the protection must not depend on the API
    endpoint (it is also called by data fixes and by the revert functions).

    TransactionTestCase, not TestCase: two threads need two database
    connections whose commits are visible to each other.
    """

    def setUp(self) -> None:
        self.user = ContributorUserFactory(username="bob")
        self.rnb_id = "XXXXYYYYZZZZ"
        Building.objects.create(rnb_id=self.rnb_id, shape=GEOSGeometry(SHAPE))

    def test_concurrent_deactivations_only_one_succeeds(self):
        """
        Input: two threads each load the same active building, wait for each
        other (barrier), then both call deactivate() on their own instance.
        Expected: exactly one call succeeds, the other raises
        OperationOnInactiveBuilding, and the history holds no extra
        deactivation.
        """
        barrier = threading.Barrier(2)
        outcomes = []

        def deactivate():
            try:
                building = Building.objects.get(rnb_id=self.rnb_id)
                barrier.wait(timeout=10)
                building.deactivate(self.user, EVENT_ORIGIN)
                outcomes.append("ok")
            except OperationOnInactiveBuilding:
                outcomes.append("inactive")
            finally:
                # each thread opens its own connection: close it ourselves
                for conn in connections.all():
                    conn.close()

        threads = [threading.Thread(target=deactivate) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertCountEqual(outcomes, ["ok", "inactive"])
        building = Building.objects.get(rnb_id=self.rnb_id)
        self.assertFalse(building.is_active)
        self.assertEqual(building.event_type, "deactivation")
        self.assertEqual(
            BuildingHistoryOnly.objects.filter(
                rnb_id=self.rnb_id, event_type="deactivation"
            ).count(),
            0,
        )
