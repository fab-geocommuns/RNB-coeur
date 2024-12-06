from django.contrib.gis.geos import Polygon
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import QuerySet, OuterRef, Subquery

from batid.models import Building, Plot
from batid.models import City
from batid.services.bdg_status import BuildingStatus


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
        # We have to order by created_at to avoid pagination issues on geographic queries
        qs = qs.order_by("created_at")

    # #######################
    # Insee Code filter

    insee_code = params.get("insee_code", None)
    if insee_code:
        city = City.objects.get(code_insee=insee_code)
        qs = qs.filter(shape__intersects=city.shape)
        # We have to order by created_at to avoid pagination issues on geographic queries
        qs = qs.order_by("created_at")

    cle_interop_ban = params.get("cle_interop_ban", None)
    if cle_interop_ban:
        qs = qs.filter(addresses_read_only__id=cle_interop_ban)
        qs = qs.order_by("created_at")

    # #######################
    # With plots (adding plots ids to the buildings
    with_plots = params.get("withPlots", None)
    if with_plots == "1":

        # Subquery to get the plots ids
        # subquery = Plot.objects.filter(shape__intersects=OuterRef("shape")).values("id")
        # qs = qs.annotate(plots=SubqueryArrayAgg(subquery, "id"))

        subquery = Plot.objects.raw(
            "SELECT id FROM batid_plot WHERE id = 'one'",
        )
        qs = qs.annotate(plots=Subquery(subquery))

    return qs


class SubqueryAggregate(Subquery):
    # https://code.djangoproject.com/ticket/10060
    template = '(SELECT %(function)s(_agg."%(column)s") FROM (%(subquery)s) _agg)'

    def __init__(self, queryset, column, output_field=None, **extra):
        if not output_field:
            # infer output_field from field type
            output_field = queryset.model._meta.get_field(column)
        super().__init__(
            queryset, output_field, column=column, function=self.function, **extra
        )


class SubqueryArrayAgg(SubqueryAggregate):
    function = "ARRAY_AGG"
