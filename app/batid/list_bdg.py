from typing import Iterable, TypeVar
from uuid import UUID

from batid.models import Address, Building, BuildingAddressesInternalIdReadOnly, City
from batid.services.bdg_status import BuildingStatus
from django.contrib.auth.models import User
from django.contrib.gis.geos import Polygon
from django.db import connection
from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404

BuildingsQuerySet = TypeVar("BuildingsQuerySet", bound=QuerySet)


def filter_bdgs_by_address(
    qs: BuildingsQuerySet,
    cle_interop: str | None = None,
    ban_id: str | UUID | None = None,
    only_without_ban_id: bool = False,
) -> BuildingsQuerySet:
    """
    Keep the buildings linked to the address matching all the given criteria.

    `cle_interop` is compared case-insensitively, through the
    address_cle_interop_upper_idx index. Since `abc` and `ABC` can both exist in
    batid_address, the filter is a subquery rather than a join: a building linked
    to both must come out only once.

    A `ban_id` which is not a UUID matches no address. Callers exposing it publicly
    are expected to refuse it beforehand, this only guards against a database error.

    With `only_without_ban_id`, the addresses holding a BAN ID are left out of the
    `cle_interop` match. It has no effect when no criterion is given.
    """
    if not cle_interop and not ban_id:
        return qs

    links = BuildingAddressesInternalIdReadOnly.objects.all()

    if cle_interop:
        links = links.filter(address__cle_interop__iexact=cle_interop)

    if only_without_ban_id:
        links = links.filter(address__ban_id__isnull=True)

    if ban_id:
        try:
            ban_uuid = UUID(str(ban_id))
        except ValueError:
            return qs.none()
        links = links.filter(address__ban_id=ban_uuid)

    return qs.filter(pk__in=links.values("building_id"))


def filter_bdgs_by_geocoded_address(
    qs: QuerySet, cle_interop: str, ban_id: str | None
) -> tuple[QuerySet, UUID | None]:
    """
    Keep the buildings linked to an address returned by the geocoder, and return
    them with the BAN ID really used to filter (None if the filter used the key).

    `Address.ban_id` is only filled for the cities with reliable BAN IDs:
    - if a local address holds the geocoded BAN ID, filter on it;
    - if no local address holds it, fall back on `cle_interop`, restricted to the
      local addresses with no BAN ID. A local address with the same key but another
      BAN ID is another address (the key has been reassigned) and must not match;
    - if the geocoder gives no valid BAN ID, nothing shows the key has been
      reassigned: fall back on `cle_interop`, whether the local address holds a BAN
      ID or not.
    """
    ban_uuid = None
    if ban_id:
        try:
            ban_uuid = UUID(str(ban_id))
        except ValueError:
            # The geocoder is an external source: treat a malformed id as absent
            ban_uuid = None

    if ban_uuid and Address.objects.filter(ban_id=ban_uuid).exists():
        return filter_bdgs_by_address(qs, ban_id=ban_uuid), ban_uuid

    return (
        filter_bdgs_by_address(
            qs, cle_interop=cle_interop, only_without_ban_id=ban_uuid is not None
        ),
        None,
    )


def list_bdgs(params, only_active=True) -> QuerySet:

    qs = Building.objects.all()

    if only_active:
        qs = qs.filter(is_active=True)

    # By default, we sort on id since the column is indexed
    qs = qs.order_by("id")

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
            status_list = BuildingStatus.ALL_TYPES_KEYS  # type: ignore[assignment]
        else:
            status_list = params["status"].split(",")

    status = [s for s in status_list if s in allowed_status]

    qs = qs.filter(status__in=status)

    # #######################
    # DEPRECATED
    # Bounding box filter
    # NB: this is the legacy bounding parameter. The format nw_lat, nw_lng, se_lat, se_lng does not respect the OGC API standard/
    # We keep it for backward compatibility.
    # This parameter is marked as obsolete in the API documentation.

    bb_str = params.get("bb", None)
    if bb_str:
        nw_lat, nw_lng, se_lat, se_lng = [float(coord) for coord in bb_str.split(",")]
        poly_coords = (
            (nw_lng, nw_lat),
            (nw_lng, se_lat),
            (se_lng, se_lat),
            (se_lng, nw_lat),
            (nw_lng, nw_lat),
        )
        poly = Polygon(poly_coords, srid=4326)

        qs = qs.filter(point__intersects=poly)
        # We have to order by created_at to avoid pagination issues on geographic queries
        qs = qs.order_by("created_at")

    # #######################
    # Bounding box filter (OGC API standard)
    bbox_str = params.get("bbox", None)
    if bbox_str:
        min_x, min_y, max_x, maxy = [float(coord) for coord in bbox_str.split(",")]
        poly_coords = (
            (min_x, min_y),
            (min_x, maxy),
            (max_x, maxy),
            (max_x, min_y),
            (min_x, min_y),
        )
        poly = Polygon(poly_coords, srid=4326)

        qs = qs.filter(point__intersects=poly)
        # We have to order by created_at to avoid pagination issues on geographic queries
        qs = qs.order_by("created_at")

    # #######################
    # Insee Code filter

    insee_code = params.get("insee_code", None)
    if insee_code:
        city = get_object_or_404(City, code_insee=insee_code)

        qs = qs.filter(point__intersects=city.shape)
        # We have to order by created_at to avoid pagination issues on geographic queries
        qs = qs.order_by("created_at")

    cle_interop_ban = params.get("cle_interop_ban", None)
    ban_id = params.get("ban_id", None)
    if cle_interop_ban or ban_id:
        qs = filter_bdgs_by_address(qs, cle_interop=cle_interop_ban, ban_id=ban_id)
        qs = qs.order_by("created_at")

    # to prevent an ugly N+1 problem on the addresses and the validated_by fields
    qs = qs.prefetch_related("addresses_internal_read_only")
    # order the validators explicitly: the M2M has no default ordering, so without
    # this the "validated_by" list comes back in a non-deterministic order.
    qs = qs.prefetch_related(
        Prefetch(
            "validated_by_read_only",
            queryset=User.objects.order_by("id"),
        )
    )

    return qs


# Plots intersecting each building of a list, with the ratio of the building shape
# covered by each plot.
#
# The filter on the extent of the buildings (`plot.shape && ST_MakeEnvelope(...)`) does
# not change the result: a plot intersecting a building always intersects the extent
# of all the buildings. It is there for the query planner: the building shapes are
# only known at execution time, so PostGIS cannot estimate `ST_Intersects` and falls
# back on a default selectivity (about 9 000 plots per building instead of 1 to 5).
# This overestimation used to trigger a costly JIT compilation on almost every call.
# The extent is a constant, which PostGIS estimates with the real statistics of
# batid_plot. It only works because Django binds parameters on the client side
# (no `server_side_binding` option): the planner sees the values as literals.
BUILDINGS_PLOTS_SQL = """
SELECT
    bdg.id,
    json_agg(
        json_build_object(
            'id', plot.id,
            'bdg_cover_ratio',
            CASE
                -- the intersection area of a point is 0, but a point is fully in its plot
                WHEN ST_GeometryType(bdg.shape) = 'ST_Point' THEN 1.0
                WHEN ST_GeometryType(bdg.shape) IN ('ST_Polygon', 'ST_MultiPolygon')
                THEN ST_Area(ST_Intersection(bdg.shape, plot.shape)) / ST_Area(bdg.shape)
                ELSE 0.0
            END
        )
        ORDER BY plot.id
    ) AS plots
FROM batid_building AS bdg
JOIN batid_plot AS plot
    ON ST_Intersects(plot.shape, bdg.shape)
    AND plot.shape && ST_MakeEnvelope(%(xmin)s, %(ymin)s, %(xmax)s, %(ymax)s, 4326)
WHERE bdg.id = ANY(%(ids)s)
GROUP BY bdg.id
"""


def attach_plots(buildings: Iterable[Building]) -> None:
    """
    Set the `plots` attribute of each building: a list of {"id", "bdg_cover_ratio"}
    for the plots it intersects, ordered by plot id, or None if it has no plot.

    Meant to be called on already loaded buildings (an API page, a single building),
    so the plots are computed in one query for all of them.
    """

    buildings = list(buildings)
    shapes = [bdg.shape for bdg in buildings if bdg.shape is not None]

    plots_by_bdg: dict[int, list[dict]] = {}
    if shapes:
        extents = [shape.extent for shape in shapes]
        params = {
            "ids": [bdg.id for bdg in buildings],
            "xmin": min(e[0] for e in extents),
            "ymin": min(e[1] for e in extents),
            "xmax": max(e[2] for e in extents),
            "ymax": max(e[3] for e in extents),
        }
        with connection.cursor() as cursor:
            cursor.execute(BUILDINGS_PLOTS_SQL, params)
            plots_by_bdg = dict(cursor.fetchall())

    for bdg in buildings:
        # plots is not a model field: it is read by the "plots" field of the serializers
        bdg.plots = plots_by_bdg.get(bdg.id)  # type: ignore[attr-defined]
