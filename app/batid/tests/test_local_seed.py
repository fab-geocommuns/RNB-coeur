from unittest import mock

from batid.models import Address, Building, City, Department
from batid.services.local_seed import (
    SeedConfigError,
    Zone,
    build_zones,
    check_target_is_local,
    count_rows,
    parse_points,
)
from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings

# Eiffel tower
LAT, LON = 48.8584, 2.2945
# ~111 m in latitude
DEG_100M = 0.001


class SeedConfigTestCase(SimpleTestCase):
    def test_parse_points(self):
        """
        Input: two points "lat,lon" separated by ";", with spaces and a trailing ";".
        Expected: a list of two (lat, lon) float tuples.
        """
        self.assertEqual(
            parse_points(" 48.8584, 2.2945 ; 45.764,4.8357;"),
            [(48.8584, 2.2945), (45.764, 4.8357)],
        )

    def test_parse_points_invalid(self):
        """
        Input: malformed strings (single value, non numeric, empty).
        Expected: a SeedConfigError for each.
        """
        for raw in ["48.85", "abc,2.29", "", " ; "]:
            with self.subTest(raw=raw):
                with self.assertRaises(SeedConfigError):
                    parse_points(raw)

    def test_build_zones(self):
        """
        Input: a point in Paris and one in La Réunion, radius 2 km.
        Expected: two zones with a 2000 m radius.
        """
        zones = build_zones([(LAT, LON), (-20.88, 55.45)], 2)
        self.assertEqual([z.radius_m for z in zones], [2000, 2000])

    def test_point_outside_france(self):
        """
        Input: a point in New York.
        Expected: a SeedConfigError.
        """
        with self.assertRaises(SeedConfigError):
            build_zones([(40.71, -74.0)], 1)

    def test_swapped_coordinates(self):
        """
        Input: the Eiffel tower given as "lon,lat".
        Expected: a SeedConfigError mentioning the inversion.
        """
        with self.assertRaisesMessage(SeedConfigError, "inversées"):
            build_zones([(LON, LAT)], 1)

    def test_invalid_radius(self):
        """
        Input: a null, negative or too large radius.
        Expected: a SeedConfigError.
        """
        for radius in [0, -1, 50]:
            with self.subTest(radius=radius):
                with self.assertRaises(SeedConfigError):
                    build_zones([(LAT, LON)], radius)

    def test_target_must_be_local_development(self):
        """
        Input: a development env with a remote db host, then a non development env
        with a local host, then a development env with a local host.
        Expected: the first two are refused, the last one is accepted.
        """
        default_db = settings.DATABASES["default"]

        with override_settings(ENVIRONMENT="development"):
            with mock.patch.dict(default_db, {"HOST": "sandbox.example.com"}):
                with self.assertRaises(SeedConfigError):
                    check_target_is_local()

        with override_settings(ENVIRONMENT="production"):
            with mock.patch.dict(default_db, {"HOST": "db"}):
                with self.assertRaises(SeedConfigError):
                    check_target_is_local()

        with override_settings(ENVIRONMENT="development"):
            with mock.patch.dict(default_db, {"HOST": "db"}):
                check_target_is_local()


def square(lat, lon, half_side_deg):
    return Polygon.from_bbox(
        (
            lon - half_side_deg,
            lat - half_side_deg,
            lon + half_side_deg,
            lat + half_side_deg,
        )
    )


class SeedSelectionTestCase(TestCase):
    """The rows selected on the source database, run against the test database."""

    def setUp(self):
        self.linked_far_address = Address.objects.create(
            cle_interop="FAR_LINKED",
            source="BAN",
            point=Point(LON, LAT + 50 * DEG_100M, srid=4326),
        )
        Address.objects.create(
            cle_interop="NEAR",
            source="BAN",
            point=Point(LON, LAT + DEG_100M, srid=4326),
        )
        Address.objects.create(
            cle_interop="FAR",
            source="BAN",
            point=Point(LON, LAT + 50 * DEG_100M, srid=4326),
        )

        # 100 m north, linked to an address located 5 km away
        Building.objects.create(
            rnb_id="NEAR0000001",
            point=Point(LON, LAT + DEG_100M, srid=4326),
            shape=square(LAT + DEG_100M, LON, 0.0001),
            addresses_internal_id=[self.linked_far_address.internal_id],
        )
        # centroid 1.3 km north, but its shape reaches the 1 km circle
        Building.objects.create(
            rnb_id="BIGSHAPE001",
            point=Point(LON, LAT + 12 * DEG_100M, srid=4326),
            shape=square(LAT + 12 * DEG_100M, LON, 0.004),
        )
        # no shape, point 300 m south
        Building.objects.create(
            rnb_id="NOSHAPE0001", point=Point(LON, LAT - 3 * DEG_100M, srid=4326)
        )
        # 5 km north
        Building.objects.create(
            rnb_id="FAR00000001",
            point=Point(LON, LAT + 50 * DEG_100M, srid=4326),
            shape=square(LAT + 50 * DEG_100M, LON, 0.0001),
        )

        City.objects.create(
            code_insee="75056",
            name="Paris",
            shape=MultiPolygon(square(LAT, LON, 0.05)),
        )
        City.objects.create(
            code_insee="69123",
            name="Lyon",
            shape=MultiPolygon(square(45.764, 4.8357, 0.05)),
        )
        Department.objects.create(
            code="75", name="Paris", shape=MultiPolygon(square(LAT, LON, 0.1))
        )

    def test_count_rows(self):
        """
        Input: a 1 km zone around the Eiffel tower; buildings at 100 m, 300 m
        (point only), 5 km and one whose centroid is 1.3 km away but whose shape
        crosses the circle; addresses at 100 m and 5 km, one of the 5 km ones
        being linked to the closest building.
        Expected: 3 buildings (not the 5 km one), 2 addresses (the near one and
        the far linked one), Paris city and department only.
        """
        zones = [Zone(lat=LAT, lon=LON, radius_m=1000)]
        counts = count_rows(connection.connection, zones)

        self.assertEqual(
            counts,
            {
                "batid_department": 1,
                "batid_department_subdivided": 0,
                "batid_city": 1,
                "batid_address": 2,
                "batid_building": 3,
            },
        )
