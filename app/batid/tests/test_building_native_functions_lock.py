from contextlib import contextmanager

from batid.exceptions import ForbiddenDjangoNativeFunction
from batid.models import Building
from batid.tests.factories.users import ContributorUserFactory
from batid.tests.helpers import coords_to_mp_geom, create_default_bdg
from django.db import InternalError
from django.test import TestCase, override_settings


@contextmanager
def native_functions_locked():
    """
    Restore the production behavior inside a test: the test runner allows the
    Django native functions on Building, this context manager relocks them.
    """
    Building._native_functions_allowed = False
    try:
        yield
    finally:
        Building._native_functions_allowed = True


# a small building in Paris, far from the Grenoble building of create_default_bdg()
PARIS_COORDS = [
    [2.349804, 48.852616],
    [2.349804, 48.852716],
    [2.349904, 48.852716],
    [2.349904, 48.852616],
    [2.349804, 48.852616],
]


class NativeFunctionsLockedTestCase(TestCase):
    """Native Django write functions must raise when the lock is active (production behavior)."""

    def setUp(self):
        self.building = create_default_bdg()

    def test_save_is_forbidden(self):
        """save() on an existing building with the lock active: raises ForbiddenDjangoNativeFunction."""
        self.building.status = "demolished"
        with native_functions_locked():
            with self.assertRaises(ForbiddenDjangoNativeFunction):
                self.building.save()

    def test_delete_is_forbidden(self):
        """delete() on an existing building with the lock active: raises ForbiddenDjangoNativeFunction."""
        with native_functions_locked():
            with self.assertRaises(ForbiddenDjangoNativeFunction):
                self.building.delete()

    def test_objects_create_is_forbidden(self):
        """Building.objects.create() with the lock active: raises, because it relies on save()."""
        with native_functions_locked():
            with self.assertRaises(ForbiddenDjangoNativeFunction):
                Building.objects.create(rnb_id="FORBIDDEN01")

    def test_queryset_update_is_forbidden(self):
        """QuerySet.update() on buildings with the lock active: raises ForbiddenDjangoNativeFunction."""
        with native_functions_locked():
            with self.assertRaises(ForbiddenDjangoNativeFunction):
                Building.objects.filter(rnb_id=self.building.rnb_id).update(
                    status="demolished"
                )

    def test_queryset_delete_is_forbidden(self):
        """QuerySet.delete() on buildings with the lock active: raises ForbiddenDjangoNativeFunction."""
        with native_functions_locked():
            with self.assertRaises(ForbiddenDjangoNativeFunction):
                Building.objects.all().delete()

    def test_bulk_create_is_forbidden(self):
        """bulk_create() of a building with the lock active: raises ForbiddenDjangoNativeFunction."""
        with native_functions_locked():
            with self.assertRaises(ForbiddenDjangoNativeFunction):
                Building.objects.bulk_create([Building(rnb_id="FORBIDDEN02")])

    def test_bulk_update_is_forbidden(self):
        """bulk_update() of a building with the lock active: raises ForbiddenDjangoNativeFunction."""
        self.building.status = "demolished"
        with native_functions_locked():
            with self.assertRaises(ForbiddenDjangoNativeFunction):
                Building.objects.bulk_update([self.building], ["status"])


@override_settings(MAX_BUILDING_AREA=float("inf"), MIN_BUILDING_AREA=0)
class BusinessFunctionsStillWorkTestCase(TestCase):
    """The RNB business functions must keep working while the lock is active."""

    def setUp(self):
        self.user = ContributorUserFactory(username="lock_test_user")

    def test_create_new_update_deactivate_work_when_locked(self):
        """
        With the lock active, a full business lifecycle (create_new, update,
        deactivate) on a building: succeeds and persists each step.
        """
        with native_functions_locked():
            building = Building.create_new(
                user=self.user,
                event_origin={"source": "test"},
                status="constructed",
                addresses_id=[],
                shape=coords_to_mp_geom(PARIS_COORDS),
                ext_ids=[],
            )
            self.assertTrue(Building.objects.filter(rnb_id=building.rnb_id).exists())

            building.update(
                user=self.user,
                event_origin={"source": "test"},
                status="notUsable",
                addresses_id=None,
            )
            building.refresh_from_db()
            self.assertEqual(building.status, "notUsable")

            building.deactivate(user=self.user, event_origin={"source": "test"})
            building.refresh_from_db()
            self.assertFalse(building.is_active)


class NativeFunctionsAllowedInTestsTestCase(TestCase):
    """The test runner lifts the lock: tests can freely use save() and delete()."""

    def test_save_works_in_tests(self):
        """save() on a building in the default test environment: succeeds and persists."""
        building = create_default_bdg()
        building.status = "demolished"
        building.save()
        building.refresh_from_db()
        self.assertEqual(building.status, "demolished")

    def test_delete_passes_the_django_lock_in_tests(self):
        """
        delete() on a building in the default test environment: the Django-level
        lock is lifted (no ForbiddenDjangoNativeFunction), but the pre-existing
        Postgres trigger prevent_building_deletion() still blocks the deletion.
        Deleting a building row is impossible in any environment, tests included.
        """
        building = create_default_bdg()
        with self.assertRaises(InternalError):
            building.delete()
