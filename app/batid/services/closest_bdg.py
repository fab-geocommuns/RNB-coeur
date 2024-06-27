from typing import Optional

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.db.models import QuerySet

from batid.models import Building
from batid.services.bdg_status import BuildingStatus


def get_closest_from_poly(poly: Polygon, radius) -> Optional[QuerySet]:
    __validate_poly(poly)
    __validate_radius(radius)

    qs = __get_real_bdg_qs()

    qs = (
        qs.extra(
            where=[
                f"ST_DWITHIN(shape::geography, ST_GeomFromText('{poly.wkt}', 4326)::geography, {radius})"
            ]
        )
        .annotate(distance=Distance("shape", poly))
        .order_by("distance")
    )

    return qs


def get_closest_from_point(lat, lng, radius) -> Optional[QuerySet]:
    __validate_point(lat, lng)
    __validate_radius(radius)
    return __get_qs(lat, lng, radius)


def __get_qs(lat, lng, radius):
    qs = (
        Building.objects.all()
        .filter(is_active=True)
        .filter(status__in=BuildingStatus.REAL_BUILDINGS_STATUS)
    )

    point_geom = Point(lng, lat, srid=4326)

    qs = (
        qs.extra(
            where=[
                f"ST_DWITHIN(shape::geography, ST_MakePoint({lng}, {lat})::geography, {radius})"
            ]
        )
        .annotate(distance=Distance("shape", point_geom))
        .order_by("distance")
    )

    return qs


def __get_real_bdg_qs():
    # todo : on devrait filtrer pour n'avoir que les bâtiments qui ont un statut de bâtiment réel
    return Building.objects.all()


def __validate_poly(poly):
    if not poly:
        raise ValueError("poly is required")
    if not isinstance(poly, Polygon):
        raise ValueError("poly must be a Polygon")
    if not poly.valid:
        raise ValueError(f"poly must be a valid Polygon ({poly.valid_reason})")


def __validate_radius(radius):
    if not radius:
        raise ValueError("radius is required")
    if not isinstance(radius, int):
        raise ValueError("radius must be an int")
    if radius < 0:
        raise ValueError("radius must be positive")


def __validate_point(lat, lng):
    # todo : les validation de latitude et de longitude sont des besoins récurrents, il faudrait les factoriser dans un module dédié

    if not lat:
        raise ValueError("lat is required")
    if not lng:
        raise ValueError("lng is required")

    if not isinstance(lat, float):
        raise ValueError("lat must be a float")
    if not isinstance(lng, float):
        raise ValueError("lng must be a float")
