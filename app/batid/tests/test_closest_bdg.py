import math
from itertools import count

from batid.models import Building
from batid.services.bdg_status import BuildingStatus
from batid.services.closest_bdg import get_closest_from_point, get_closest_from_poly
from django.contrib.gis.geos import Point, Polygon
from django.db import connection
from django.test import TestCase

# (lat, lng) of centres in metropolitan France and in the 5 DROM
CENTRES = {
    "Paris": (48.8566, 2.3522),
    "Dunkerque": (51.0344, 2.3768),
    "Cayenne": (4.9372, -52.326),
    "Pointe-à-Pitre": (16.2411, -61.5331),
    "Saint-Denis (La Réunion)": (-20.8789, 55.4481),
    "Mamoudzou": (-12.7806, 45.2279),
}
RADII = [5, 50, 1000]
# Fractions of the radius at which buildings are placed, inside and outside
FRACTIONS = [0.5, 0.98, 1.02, 1.5]
AZIMUTHS = range(0, 360, 45)

_rnb_ids = count()


def project(*, lat: float, lng: float, distance_m: float, azimuth_deg: float) -> Point:
    """Point at distance_m metres from (lat, lng) towards azimuth_deg, on the ellipsoid."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_X(g), ST_Y(g) FROM (SELECT ST_Project("
            "ST_MakePoint(%s, %s)::geography, %s, radians(%s))::geometry AS g) s",
            [lng, lat, distance_m, azimuth_deg],
        )
        x, y = cursor.fetchone()
    return Point(x, y, srid=4326)


def point_building(point: Point) -> Building:
    return Building(
        rnb_id=f"T{next(_rnb_ids):011d}",
        shape=point,
        point=point,
        status="constructed",
        is_active=True,
    )


def square_around(*, lat: float, lng: float, half_side_m: float) -> Polygon:
    dlat = half_side_m / 111_320
    dlng = half_side_m / (111_320 * math.cos(math.radians(lat)))
    poly = Polygon.from_bbox((lng - dlng, lat - dlat, lng + dlng, lat + dlat))
    poly.srid = 4326
    return poly


# The reference queries are the SQL used before the bbox pre-filter, verbatim
def reference_from_point(*, lat: float, lng: float, radius: float) -> set[str]:
    return _reference(
        where="ST_DWithin(shape::geography, ST_MakePoint(%s, %s)::geography, %s)",
        params=[lng, lat, radius],
    )


def reference_from_poly(*, poly: Polygon, radius: float) -> set[str]:
    return _reference(
        where="ST_DWithin(shape::geography, ST_GeomFromWKB(%s, 4326), %s)",
        params=[poly.wkb, radius],
    )


def _reference(*, where: str, params: list) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rnb_id FROM batid_building "
            f"WHERE {where} AND is_active = true AND status = ANY(%s)",  # nosec B608: static SQL
            [*params, BuildingStatus.REAL_BUILDINGS_STATUS],
        )
        return {row[0] for row in cursor.fetchall()}


class ClosestBuildingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Building.objects.bulk_create(
            point_building(
                project(lat=lat, lng=lng, distance_m=f * r, azimuth_deg=azimuth)
            )
            for lat, lng in CENTRES.values()
            for r in RADII
            for f in FRACTIONS
            for azimuth in AZIMUTHS
        )

    def test_same_buildings_as_before_point(self):
        """
        Input: point buildings at 0.5, 0.98, 1.02 and 1.5 times 5, 50 and 1000 m, on 8
        azimuths, around 6 centres (metropole and the 5 DROM); a closest search from
        each centre with each radius.
        Expected: get_closest_from_point returns the same non-empty set of buildings as
        the query without the bbox pre-filter.
        """
        for name, (lat, lng) in CENTRES.items():
            for radius in RADII:
                with self.subTest(centre=name, radius=radius):
                    found = set(
                        get_closest_from_point(lat, lng, radius).values_list(
                            "rnb_id", flat=True
                        )
                    )

                    expected = reference_from_point(lat=lat, lng=lng, radius=radius)
                    self.assertTrue(expected)
                    self.assertEqual(found, expected)

    def test_same_buildings_as_before_polygon(self):
        """
        Input: the same buildings; a closest search from a ~10 m square around each
        centre, with a 35 m and a 1000 m radius.
        Expected: get_closest_from_poly returns the same non-empty set of buildings as
        the query without the bbox pre-filter.
        """
        for name, (lat, lng) in CENTRES.items():
            poly = square_around(lat=lat, lng=lng, half_side_m=5)
            for radius in [35, 1000]:
                with self.subTest(centre=name, radius=radius):
                    found = set(
                        get_closest_from_poly(poly, radius).values_list(
                            "rnb_id", flat=True
                        )
                    )

                    expected = reference_from_poly(poly=poly, radius=radius)
                    self.assertTrue(expected)
                    self.assertEqual(found, expected)

    def test_edge_east_at_51n_needs_latitude_cosine(self):
        """
        Input: a building at 0.99 x 50 m due east of a point at 51.0344 N; a 50 m
        closest search from that point.
        Expected: the building is returned. Fails if the bbox ignores the cosine of the
        latitude (a degree of longitude is only ~70 km there).
        """
        lat, lng = 51.0344, 2.3768
        bdg = point_building(
            project(lat=lat, lng=lng, distance_m=0.99 * 50, azimuth_deg=90)
        )
        bdg.save()

        found = get_closest_from_point(lat, lng, 50).values_list("rnb_id", flat=True)

        self.assertIn(bdg.rnb_id, found)

    def test_edge_north_at_4n_needs_margin(self):
        """
        Input: a building at 0.999 x 1000 m due north of a point at 4.0 N; a 1000 m
        closest search from that point.
        Expected: the building is returned. Fails without the 10 % margin (a degree of
        latitude is shorter than 111,320 m near the equator).
        """
        lat, lng = 4.0, -52.33
        bdg = point_building(
            project(lat=lat, lng=lng, distance_m=0.999 * 1000, azimuth_deg=0)
        )
        bdg.save()

        found = get_closest_from_point(lat, lng, 1000).values_list("rnb_id", flat=True)

        self.assertIn(bdg.rnb_id, found)
