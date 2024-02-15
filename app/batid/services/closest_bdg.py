from typing import Optional
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.db.models import QuerySet

from batid.models import Building


def get_closest(lat, lng, radius) -> Optional[QuerySet]:
    __validate(lat, lng, radius)
    return __get_qs(lat, lng, radius)


def __get_qs(lat, lng, radius):
    qs = Building.objects.all()

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


def __validate(lat, lng, radius):
    # todo : les validation de latitude et de longitude sont des besoins récurrents, il faudrait les factoriser dans un module dédié

    if not lat:
        raise ValueError("lat is required")
    if not lng:
        raise ValueError("lng is required")
    if not radius:
        raise ValueError("radius is required")
    if not isinstance(lat, float):
        raise ValueError("lat must be a float")
    if not isinstance(lng, float):
        raise ValueError("lng must be a float")
    if not isinstance(radius, int):
        raise ValueError("radius must be an int")
    if radius < 0:
        raise ValueError("radius must be positive")
