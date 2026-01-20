from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from django.test import TestCase

from batid.exceptions import BuildingOverlapError
from batid.models import Building
from batid.services.building_overlap import (
    check_building_overlap,
)
from batid.tests.factories.users import ContributorUserFactory


# Realistic base coordinates (Paris, ~10m x 10m)
# In WGS84, 0.0001 degree ≈ 11m at Paris latitude
BASE_LON = 2.3522  # Paris longitude
BASE_LAT = 48.8566  # Paris latitude
SMALL_OFFSET = 0.0001  # ~11m
LARGE_OFFSET = 0.001  # ~110m


def make_polygon(x1, y1, x2, y2, srid=4326):
    """Create a rectangular polygon with given coordinates."""
    wkt = (
        f"SRID={srid};POLYGON(({x1} {y1}, {x1} {y2}, {x2} {y2}, {x2} {y1}, {x1} {y1}))"
    )
    return GEOSGeometry(wkt)


def make_small_building_shape(offset_lon=0, offset_lat=0):
    """Create a small building (~10m x 10m) from base coordinates."""
    x1 = BASE_LON + offset_lon
    y1 = BASE_LAT + offset_lat
    x2 = x1 + SMALL_OFFSET
    y2 = y1 + SMALL_OFFSET
    return make_polygon(x1, y1, x2, y2)


def make_large_building_shape(offset_lon=0, offset_lat=0):
    """Create a large building (~100m x 100m) from base coordinates."""
    x1 = BASE_LON + offset_lon
    y1 = BASE_LAT + offset_lat
    x2 = x1 + LARGE_OFFSET
    y2 = y1 + LARGE_OFFSET
    return make_polygon(x1, y1, x2, y2)


@override_settings(MAX_BUILDING_AREA=float("inf"), MIN_BUILDING_AREA=0)
class TestBuildingOverlapService(TestCase):
    """Tests for the building overlap check service."""

    def setUp(self):
        self.user = ContributorUserFactory(username="test_overlap_user")

    def test_no_overlap_no_error(self):
        """A building without overlap should not raise an error."""
        # Create an existing building
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_small_building_shape(),
            is_active=True,
            status="constructed",
        )

        # New geometry completely separate (far away)
        new_shape = make_small_building_shape(offset_lon=0.01, offset_lat=0.01)

        # Should not raise an error
        check_building_overlap(new_shape)

    def test_small_overlap_no_error(self):
        """An overlap below the threshold should not raise an error."""
        # Create an existing building
        existing_shape = make_small_building_shape()
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=existing_shape,
            is_active=True,
            status="constructed",
        )

        # New geometry with small overlap (~20% coverage)
        # Offset by 80% of the building size
        new_shape = make_small_building_shape(
            offset_lon=SMALL_OFFSET * 0.8, offset_lat=0
        )

        # Should not raise an error because overlap < 80%
        check_building_overlap(new_shape)

    def test_large_overlap_new_in_existing_raises_error(self):
        """A new building too included in an existing one should raise an error."""
        # Create a large existing building
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_large_building_shape(),
            is_active=True,
            status="constructed",
        )

        # New small building completely included in the existing one
        # (at the center of the large one)
        new_shape = make_small_building_shape(
            offset_lon=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
            offset_lat=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
        )

        # Should raise BuildingOverlapError (100% of new is in existing)
        with self.assertRaises(BuildingOverlapError) as context:
            check_building_overlap(new_shape)

        self.assertEqual(len(context.exception.overlapping_buildings), 1)
        self.assertEqual(
            context.exception.overlapping_buildings[0]["rnb_id"], "EXISTING001"
        )
        self.assertEqual(
            context.exception.overlapping_buildings[0]["overlap_ratio"], 1.0
        )

    def test_large_overlap_existing_in_new_raises_error(self):
        """An existing building too included in the new one should raise an error."""
        # Create a small existing building (at the center of where the large one will be)
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_small_building_shape(
                offset_lon=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
                offset_lat=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
            ),
            is_active=True,
            status="constructed",
        )

        # New large building that encompasses the existing one
        new_shape = make_large_building_shape()

        # Should raise BuildingOverlapError (100% of existing is in new)
        with self.assertRaises(BuildingOverlapError) as context:
            check_building_overlap(new_shape)

        self.assertEqual(len(context.exception.overlapping_buildings), 1)
        self.assertEqual(
            context.exception.overlapping_buildings[0]["rnb_id"], "EXISTING001"
        )

    def test_inactive_building_ignored(self):
        """Inactive buildings should not be considered."""
        # Create an inactive building
        Building.objects.create(
            rnb_id="INACTIVE001",
            shape=make_large_building_shape(),
            is_active=False,  # Inactive
            status="constructed",
        )

        # New building that overlaps the inactive one
        new_shape = make_small_building_shape(
            offset_lon=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
            offset_lat=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
        )

        # Should not raise an error because the existing building is inactive
        check_building_overlap(new_shape)

    def test_non_real_status_ignored(self):
        """Buildings with status outside REAL_BUILDINGS_STATUS should be ignored."""
        # Create a building with "demolished" status (not in REAL_BUILDINGS_STATUS)
        Building.objects.create(
            rnb_id="DEMOLISHED",
            shape=make_large_building_shape(),
            is_active=True,
            status="demolished",  # Not in REAL_BUILDINGS_STATUS
        )

        # New building that overlaps the demolished one
        new_shape = make_small_building_shape(
            offset_lon=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
            offset_lat=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
        )

        # Should not raise an error because "demolished" is not a "real" status
        check_building_overlap(new_shape)

    def test_point_geometry_skipped(self):
        """Point geometries should not be checked."""
        # Create an existing building
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_large_building_shape(),
            is_active=True,
            status="constructed",
        )

        # Point at the center of the existing building
        center_lon = BASE_LON + LARGE_OFFSET / 2
        center_lat = BASE_LAT + LARGE_OFFSET / 2
        new_shape = GEOSGeometry(f"SRID=4326;POINT({center_lon} {center_lat})")

        # Should not raise an error because points have no area
        check_building_overlap(new_shape)

    def test_none_shape_skipped(self):
        """A None shape should not raise an error."""
        check_building_overlap(None)

    def test_multiple_overlapping_buildings(self):
        """Multiple conflicting buildings should all be listed."""
        # Create two small existing buildings in the area of the future large one
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_small_building_shape(
                offset_lon=LARGE_OFFSET * 0.2, offset_lat=LARGE_OFFSET * 0.2
            ),
            is_active=True,
            status="constructed",
        )
        Building.objects.create(
            rnb_id="EXISTING002",
            shape=make_small_building_shape(
                offset_lon=LARGE_OFFSET * 0.6, offset_lat=LARGE_OFFSET * 0.2
            ),
            is_active=True,
            status="constructed",
        )

        # Large new building that encompasses both
        new_shape = make_large_building_shape()

        with self.assertRaises(BuildingOverlapError) as context:
            check_building_overlap(new_shape)

        # Both buildings should be listed
        rnb_ids = [b["rnb_id"] for b in context.exception.overlapping_buildings]
        self.assertIn("EXISTING001", rnb_ids)
        self.assertIn("EXISTING002", rnb_ids)

    def test_error_message_format(self):
        """The error message should contain conflict details."""
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_small_building_shape(
                offset_lon=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
                offset_lat=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
            ),
            is_active=True,
            status="constructed",
        )

        new_shape = make_large_building_shape()

        with self.assertRaises(BuildingOverlapError) as context:
            check_building_overlap(new_shape)

        # Check the message format
        message = context.exception.api_message_with_details()
        self.assertIn("EXISTING001", message)
        self.assertIn("%", message)  # Percentage should be present


@override_settings(MAX_BUILDING_AREA=float("inf"), MIN_BUILDING_AREA=0)
class TestBuildingOverlapIntegration(TestCase):
    """Integration tests with Building model methods."""

    def setUp(self):
        self.user = ContributorUserFactory(username="test_overlap_user")

    def test_create_new_with_overlap_raises_error(self):
        """Building.create_new should raise an error if overlap is too large."""
        # Create a large existing building
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_large_building_shape(),
            is_active=True,
            status="constructed",
        )

        # Try to create a small building included in the existing one
        new_shape = make_small_building_shape(
            offset_lon=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
            offset_lat=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
        )

        with self.assertRaises(BuildingOverlapError):
            Building.create_new(
                user=self.user,
                event_origin={"source": "test"},
                status="constructed",
                addresses_id=[],
                shape=new_shape,
                ext_ids=[],
            )

    def test_create_new_without_overlap_succeeds(self):
        """Building.create_new should succeed without overlap."""
        # Create an existing building
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_small_building_shape(),
            is_active=True,
            status="constructed",
        )

        # Create a new separate building (far away)
        new_shape = make_small_building_shape(offset_lon=0.01, offset_lat=0.01)

        building = Building.create_new(
            user=self.user,
            event_origin={"source": "test"},
            status="constructed",
            addresses_id=[],
            shape=new_shape,
            ext_ids=[],
        )

        self.assertIsNotNone(building)
        self.assertTrue(building.is_active)

    def test_update_shape_with_overlap_raises_error(self):
        """Building.update with overlapping shape should raise an error."""
        # Create a large existing building at base coordinates (~110m x 110m)
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=make_large_building_shape(),
            is_active=True,
            status="constructed",
        )

        # Create a small building at the edge of the large one
        building_to_update = Building.objects.create(
            rnb_id="TOUPDATE001",
            shape=make_small_building_shape(offset_lon=0, offset_lat=-SMALL_OFFSET),
            is_active=True,
            status="constructed",
        )

        # Move the building fully inside the large one (100% overlap)
        overlapping_shape = make_small_building_shape()

        with self.assertRaises(BuildingOverlapError):
            building_to_update.update(
                user=self.user,
                event_origin={"source": "test"},
                status=None,
                addresses_id=None,
                shape=overlapping_shape,
            )

    def test_update_without_shape_change_no_check(self):
        """Building.update without shape change should not check overlap."""
        # Create a large "container" building
        Building.objects.create(
            rnb_id="CONTAINER01",
            shape=make_large_building_shape(),
            is_active=True,
            status="constructed",
        )
        # Create a small building included in the container (initial "invalid" state)
        building = Building.objects.create(
            rnb_id="CONTAINED01",
            shape=make_small_building_shape(
                offset_lon=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
                offset_lat=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
            ),
            is_active=True,
            status="constructed",
        )

        # Update only the status (not the shape)
        # Should not raise an error
        building.update(
            user=self.user,
            event_origin={"source": "test"},
            status="ongoingChange",
            addresses_id=None,
            shape=None,  # No shape change
        )

        building.refresh_from_db()
        self.assertEqual(building.status, "ongoingChange")

    def test_split_with_non_overlapping_children_succeeds(self):
        """Building.split should succeed when children don't overlap existing buildings."""
        # Create a building to split (~20m x 20m)
        parent_shape = make_polygon(
            BASE_LON,
            BASE_LAT,
            BASE_LON + SMALL_OFFSET * 2,
            BASE_LAT + SMALL_OFFSET * 2,
        )
        parent = Building.objects.create(
            rnb_id="PARENT00001",
            shape=parent_shape,
            is_active=True,
            status="constructed",
            ext_ids=[],
        )

        # Split into two contiguous parts (no other existing buildings)
        child1_shape = make_polygon(
            BASE_LON,
            BASE_LAT,
            BASE_LON + SMALL_OFFSET,
            BASE_LAT + SMALL_OFFSET * 2,
        )
        child2_shape = make_polygon(
            BASE_LON + SMALL_OFFSET,
            BASE_LAT,
            BASE_LON + SMALL_OFFSET * 2,
            BASE_LAT + SMALL_OFFSET * 2,
        )

        created_buildings = [
            {
                "status": "constructed",
                "addresses_cle_interop": [],
                "shape": child1_shape.wkt,
            },
            {
                "status": "constructed",
                "addresses_cle_interop": [],
                "shape": child2_shape.wkt,
            },
        ]

        # Should succeed because parent is deactivated before children are created
        # and no other buildings exist in this area
        children = parent.split(
            created_buildings=created_buildings,
            user=self.user,
            event_origin={"source": "test"},
        )

        self.assertEqual(len(children), 2)
        for child in children:
            self.assertTrue(child.is_active)

    def test_split_with_overlapping_child_raises_error(self):
        """Building.split should raise an error if a child overlaps an existing building."""
        # Create a large building to split
        parent_shape = make_large_building_shape()
        parent = Building.objects.create(
            rnb_id="PARENT00001",
            shape=parent_shape,
            is_active=True,
            status="constructed",
            ext_ids=[],
        )

        # Create another existing building (small, at the center of where parent is)
        # This will be completely encompassed by one of the children
        existing_shape = make_small_building_shape(
            offset_lon=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
            offset_lat=LARGE_OFFSET / 2 - SMALL_OFFSET / 2,
        )
        Building.objects.create(
            rnb_id="EXISTING001",
            shape=existing_shape,
            is_active=True,
            status="constructed",
        )

        # Try to split where one child completely encompasses EXISTING001
        # First child: left half of parent
        child1_shape = make_polygon(
            BASE_LON,
            BASE_LAT,
            BASE_LON + LARGE_OFFSET / 2,
            BASE_LAT + LARGE_OFFSET,
        )
        # Second child: right half of parent (this one will contain EXISTING001)
        child2_shape = make_polygon(
            BASE_LON + LARGE_OFFSET / 2 - SMALL_OFFSET,  # Overlap with EXISTING001
            BASE_LAT,
            BASE_LON + LARGE_OFFSET,
            BASE_LAT + LARGE_OFFSET,
        )

        created_buildings = [
            {
                "status": "constructed",
                "addresses_cle_interop": [],
                "shape": child1_shape.wkt,
            },
            {
                "status": "constructed",
                "addresses_cle_interop": [],
                "shape": child2_shape.wkt,
            },
        ]

        with self.assertRaises(BuildingOverlapError):
            parent.split(
                created_buildings=created_buildings,
                user=self.user,
                event_origin={"source": "test"},
            )

    def test_split_with_overlapping_children_raises_error(self):
        """Building.split should raise an error if children overlap each other."""
        # Create a building to split (~20m x 20m)
        parent_shape = make_polygon(
            BASE_LON,
            BASE_LAT,
            BASE_LON + SMALL_OFFSET * 2,
            BASE_LAT + SMALL_OFFSET * 2,
        )
        parent = Building.objects.create(
            rnb_id="PARENT00001",
            shape=parent_shape,
            is_active=True,
            status="constructed",
            ext_ids=[],
        )

        # Create two children that overlap each other significantly (>80%)
        # Child 1: covers most of the parent
        child1_shape = make_polygon(
            BASE_LON,
            BASE_LAT,
            BASE_LON + SMALL_OFFSET * 1.8,
            BASE_LAT + SMALL_OFFSET * 2,
        )
        # Child 2: also covers most of the parent, overlapping with child 1
        child2_shape = make_polygon(
            BASE_LON + SMALL_OFFSET * 0.2,
            BASE_LAT,
            BASE_LON + SMALL_OFFSET * 2,
            BASE_LAT + SMALL_OFFSET * 2,
        )

        created_buildings = [
            {
                "status": "constructed",
                "addresses_cle_interop": [],
                "shape": child1_shape.wkt,
            },
            {
                "status": "constructed",
                "addresses_cle_interop": [],
                "shape": child2_shape.wkt,
            },
        ]

        # Should raise BuildingOverlapError because child2 overlaps child1
        with self.assertRaises(BuildingOverlapError):
            parent.split(
                created_buildings=created_buildings,
                user=self.user,
                event_origin={"source": "test"},
            )
