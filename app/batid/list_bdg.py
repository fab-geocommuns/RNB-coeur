from django.contrib.gis.geos import Polygon

from batid.models import Building
from batid.models import City
from batid.services.bdg_status import BuildingStatus


def list_bdgs(params):
    qs = Building.objects.all().filter(is_active=True)

    # #######################
    # Status filter

    # User "permissions" for building status
    allowed_status = BuildingStatus.PUBLIC_TYPES_KEYS
    if "user" in params and params["user"].is_authenticated:
        allowed_status = BuildingStatus.ALL_TYPES_KEYS

    # Queries status and filter on allowed status
    status_list = BuildingStatus.REAL_BUILDINGS_STATUS
    if "status" in params:
        if params["status"] == "all":
            status_list = BuildingStatus.ALL_TYPES_KEYS
        else:
            status_list = params["status"].split(",")

    status = [s for s in status_list if s in allowed_status]

    qs = qs.filter(status__in=status)

    # #######################
    # Bounding box filter

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

    # #######################
    # Insee Code filter

    insee_code = params.get("insee_code", None)
    if insee_code:
        city = City.objects.get(code_insee=insee_code)
        qs = qs.filter(shape__intersects=city.shape)

    return qs.order_by()
