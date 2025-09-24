from typing import Optional

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.db.models import BooleanField
from django.db.models import ExpressionWrapper
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL

from batid.models import Building
from batid.services.bdg_status import BuildingStatus


def get_closest_from_poly(poly: Polygon, radius) -> Optional[QuerySet]:
    __validate_poly(poly)
    __validate_radius(radius)

    qs = __get_real_bdg_qs()

    qs = (
        qs.filter(
            ExpressionWrapper(
                RawSQL(
                    "ST_DWithin(shape::geography, ST_GeomFromWKB(%s, 4326), %s)",
                    (poly.wkb, radius),
                ),
                output_field=BooleanField(),
            )
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
    qs = __get_real_bdg_qs()

    point_geom = Point(lng, lat, srid=4326)

    where_sql = "ST_DWithin(shape::geography, ST_MakePoint(%s, %s)::geography, %s)"

    qs = (
        qs.extra(  # nosec B610: params are properly escaped. Better yet: use filter
            where=[where_sql], params=[lng, lat, radius]
        )
        .annotate(distance=Distance("shape", point_geom))
        .order_by("distance")
    )

    qs = qs.prefetch_related("addresses_read_only")
    return qs


def __get_real_bdg_qs():
    return (
        Building.objects.all()
        .filter(is_active=True)
        .filter(status__in=BuildingStatus.REAL_BUILDINGS_STATUS)
    )


def __validate_poly(poly):
    if not poly:
        raise ValueError("poly is required")
    if not isinstance(poly, Polygon):
        raise ValueError("poly must be a Polygon")
    if not poly.valid:
        raise ValueError(f"poly must be a valid Polygon ({poly.valid_reason})")


def __validate_radius(radius):
    if radius is None:
        raise ValueError("radius is required")
    if not isinstance(radius, float) and not isinstance(radius, int):
        raise ValueError("radius must be a number")
    if radius < 0:
        raise ValueError("radius must be positive")


def __validate_point(lat, lng):
    # todo : les validation de latitude et de longitude sont des besoins récurrents, il faudrait les factoriser dans un module dédié

    if not lat:
        raise ValueError("lat is required")
    if not lng:
        raise ValueError("lng is required")

    if not isinstance(lat, float):
        raise ValueError(f"lat must be a float, given value = {lat}")
    if not isinstance(lng, float):
        raise ValueError(f"lng must be a float, given value = {lng}")
