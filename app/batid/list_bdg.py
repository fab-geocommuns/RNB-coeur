from django.contrib.gis.geos import Polygon
from django.db.models import QuerySet
from batid.services.bdg_status import BuildingStatus
from batid.models import Building, City


def public_bdg_queryset(user=None) -> QuerySet:
    allowed_status = BuildingStatus.PUBLIC_TYPES_KEYS

    if user and user.is_authenticated:
        allowed_status = BuildingStatus.ALL_TYPES_KEYS

    return (
        Building.objects.filter(status__type__in=allowed_status)
        .order_by("id")
        .distinct("id")
    )


def filter_bdg_queryset(qs: QuerySet, params) -> QuerySet:
    # Bounding box
    bbox_str = params.get("bb", None)
    if bbox_str:
        nw_lat, nw_lng, se_lat, se_lng = [float(coord) for coord in bbox_str.split(",")]
        poly_coords = (
            (nw_lng, nw_lat),
            (nw_lng, se_lat),
            (se_lng, se_lat),
            (se_lng, nw_lat),
            (nw_lng, nw_lat),
        )
        poly = Polygon(poly_coords, srid=4326)
        qs = qs.filter(shape__intersects=poly)

    # Insee Code filter
    insee_code = params.get("insee_code", None)
    if insee_code:
        city = City.objects.get(code_insee=insee_code)
        qs = qs.filter(shape__intersects=city.shape)

    # Status filter
    status = BuildingStatus.DEFAULT_DISPLAY_STATUS

    query_status_str = params.get("status", None)

    if query_status_str:
        if query_status_str == "all":
            status = BuildingStatus.ALL_TYPES_KEYS
        else:
            status = query_status_str.split(",")

    qs = qs.filter(status__type__in=status, status__is_current=True)

    return qs
