from batid.models import Building
from batid.services.bdg_status import BuildingStatus
from django.contrib.gis.db.models.functions import Intersection, Union
from django.contrib.gis.geos import Polygon
from django.db.models import Case, F, FloatField, Func, Value, When
from django.db.models.lookups import Exact


def get_buildings_intersecting_polygon(poly: Polygon):
    def surface_metric(default):
        # Buildings whose shape is a mere point have no known footprint:
        # surface metrics are unknown (null), not 0.
        return Case(
            When(
                Exact(Func(F("shape"), function="ST_AREA"), 0),
                then=Value(None),
            ),
            default=default,
            output_field=FloatField(),
        )

    intersection_area = Func(Intersection("shape", poly), function="ST_AREA")

    qs = (
        Building.objects.filter(is_active=True)
        .filter(status__in=BuildingStatus.REAL_BUILDINGS_STATUS)
        .filter(shape__intersects=poly)
        .annotate(
            iou=surface_metric(
                intersection_area / Func(Union("shape", poly), function="ST_AREA")
            ),
            input_covered_by_rnb=surface_metric(intersection_area / Value(poly.area)),
            rnb_covered_by_input=surface_metric(
                intersection_area / Func(F("shape"), function="ST_AREA")
            ),
        )
        .order_by(F("iou").desc(nulls_last=True), "rnb_id")
    )

    qs = qs.prefetch_related("addresses_read_only")
    qs = qs.prefetch_related("validated_by_read_only")

    return qs
