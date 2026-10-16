from datetime import timedelta

from batid.models import (
    City,
    Department,
    Department_subdivided,
    EditionActivity,
    Organization,
)
from batid.models.building import Building
from batid.services.edition_activity import (
    record_edition_activity,
    record_recent_edition_activity,
)
from batid.tests.factories.users import ContributorUserFactory, UserFactory
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase, override_settings
from django.utils import timezone

# square around (0, 0), covering INSIDE_POLYGON and INSIDE_NEIGHBOUR_POLYGON
AREA_COORDS = "-0.01 -0.01, -0.01 0.01, 0.01 0.01, 0.01 -0.01, -0.01 -0.01"

INSIDE_POLYGON = GEOSGeometry(
    "POLYGON((0 0, 0 0.001, 0.001 0.001, 0.001 0, 0 0))", srid=4326
)
# contiguous to INSIDE_POLYGON, so both can be merged
INSIDE_NEIGHBOUR_POLYGON = GEOSGeometry(
    "POLYGON((0.001 0, 0.001 0.001, 0.002 0.001, 0.002 0, 0.001 0))", srid=4326
)
OUTSIDE_POLYGON = GEOSGeometry(
    "POLYGON((1 1, 1 1.001, 1.001 1.001, 1.001 1, 1 1))", srid=4326
)


def create_building(user, shape, source="contribution"):
    return Building.create_new(
        user=user,
        event_origin={"source": source},
        status="constructed",
        addresses_cle_interop=[],
        shape=shape,
        ext_ids=[],
    )


# No freezegun: sys_period is set by a PostgreSQL trigger using CURRENT_TIMESTAMP.
@override_settings(MAX_BUILDING_AREA=float("inf"))
class RecordEditionActivityTestCase(TestCase):
    def setUp(self):
        self.city = City.objects.create(
            code_insee="99001",
            name="Ville Test",
            shape=GEOSGeometry(f"MULTIPOLYGON((({AREA_COORDS})))", srid=4326),
        )
        self.department = Department.objects.create(
            code="99",
            name="Département Test",
            shape=GEOSGeometry(f"MULTIPOLYGON((({AREA_COORDS})))", srid=4326),
        )
        Department_subdivided.objects.create(
            code="99",
            name="Département Test",
            shape=GEOSGeometry(f"POLYGON(({AREA_COORDS}))", srid=4326),
        )
        self.since = timezone.now() - timedelta(minutes=1)

    def record(self):
        return record_edition_activity(
            self.since, timezone.now() + timedelta(minutes=1)
        )

    def test_one_row_per_contribution_event(self):
        """
        Input: user A creates a building then updates it, user B creates a building
        (3 contribution events).
        Expected: 3 rows, with the right user and event_type for each event.
        """
        user_a = ContributorUserFactory(username="user_a")
        user_b = ContributorUserFactory(username="user_b")
        bdg = create_building(user_a, INSIDE_POLYGON)
        bdg.update(
            user=user_a,
            event_origin={"source": "contribution"},
            status="demolished",
            addresses_cle_interop=None,
        )
        create_building(user_b, OUTSIDE_POLYGON)

        inserted = self.record()

        self.assertEqual(inserted, 3)
        # all events share the same edited_at (one test transaction), so order is not checked
        self.assertCountEqual(
            [(r.user.username, r.event_type) for r in EditionActivity.objects.all()],
            [
                ("user_a", "creation"),
                ("user_a", "update"),
                ("user_b", "creation"),
            ],
        )

    def test_non_contribution_sources_are_ignored(self):
        """
        Input: one building created by an import and one by a data fix.
        Expected: no row is recorded.
        """
        user = UserFactory(username="rnb_team")
        create_building(user, INSIDE_POLYGON, source="import")
        create_building(user, OUTSIDE_POLYGON, source="data_fix")

        self.assertEqual(self.record(), 0)
        self.assertEqual(EditionActivity.objects.count(), 0)

    def test_city_and_department_are_resolved_from_the_building_point(self):
        """
        Input: one building created inside the test city/department, one outside.
        Expected: the first row has the city and department, the second has none.
        """
        user = ContributorUserFactory()
        inside = create_building(user, INSIDE_POLYGON)
        outside = create_building(user, OUTSIDE_POLYGON)

        self.record()

        inside_row = EditionActivity.objects.get(event_id=inside.event_id)
        self.assertEqual(inside_row.city, self.city)
        self.assertEqual(inside_row.department, self.department)
        outside_row = EditionActivity.objects.get(event_id=outside.event_id)
        self.assertIsNone(outside_row.city)
        self.assertIsNone(outside_row.department)

    def test_organization_of_the_user_is_recorded(self):
        """
        Input: a user belonging to "Mairie de Test" creates a building,
        a user without organization creates another one.
        Expected: the rows carry the organization, and None respectively.
        """
        with_org = ContributorUserFactory()
        organization = Organization.objects.create(name="Mairie de Test")
        with_org.profile.organization = organization
        with_org.profile.save()
        without_org = ContributorUserFactory()

        bdg_with_org = create_building(with_org, INSIDE_POLYGON)
        bdg_without_org = create_building(without_org, OUTSIDE_POLYGON)

        self.record()

        self.assertEqual(
            EditionActivity.objects.get(event_id=bdg_with_org.event_id).organization,
            organization,
        )
        self.assertIsNone(
            EditionActivity.objects.get(event_id=bdg_without_org.event_id).organization
        )

    def test_merge_touching_several_buildings_counts_once(self):
        """
        Input: 2 buildings created by an import, then merged by a contributor
        (one event touching 3 building rows).
        Expected: a single "merge" row, located in the test city.
        """
        importer = UserFactory(username="rnb_team")
        contributor = ContributorUserFactory()
        bdg_1 = create_building(importer, INSIDE_POLYGON, source="import")
        bdg_2 = create_building(importer, INSIDE_NEIGHBOUR_POLYGON, source="import")
        merged = Building.merge(
            [bdg_1, bdg_2],
            user=contributor,
            event_origin={"source": "contribution"},
            status="constructed",
            addresses_cle_interop=[],
        )

        self.assertEqual(self.record(), 1)
        row = EditionActivity.objects.get()
        self.assertEqual(row.event_id, merged.event_id)
        self.assertEqual(row.event_type, "merge")
        self.assertEqual(row.user, contributor)
        self.assertEqual(row.city, self.city)

    def test_recording_twice_does_not_duplicate_rows(self):
        """
        Input: one contribution event, recorded twice over the same time range.
        Expected: 1 row inserted the first time, 0 the second time.
        """
        create_building(ContributorUserFactory(), INSIDE_POLYGON)

        self.assertEqual(self.record(), 1)
        self.assertEqual(self.record(), 0)
        self.assertEqual(EditionActivity.objects.count(), 1)

    def test_editions_outside_the_time_range_are_ignored(self):
        """
        Input: one contribution event made now, recorded over a range ending before it.
        Expected: no row is recorded.
        """
        create_building(ContributorUserFactory(), INSIDE_POLYGON)

        inserted = record_edition_activity(self.since - timedelta(days=1), self.since)

        self.assertEqual(inserted, 0)

    def test_incremental_run_records_new_editions_only(self):
        """
        Input: one contribution event, an incremental run, then a second event
        and another incremental run.
        Expected: the first run records 1 row, the second run records only the new one.
        """
        user = ContributorUserFactory()
        create_building(user, INSIDE_POLYGON)
        self.assertEqual(record_recent_edition_activity(), 1)

        create_building(user, OUTSIDE_POLYGON)
        self.assertEqual(record_recent_edition_activity(), 1)

        self.assertEqual(EditionActivity.objects.count(), 2)
