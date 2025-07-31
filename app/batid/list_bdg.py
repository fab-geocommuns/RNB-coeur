from django.contrib.gis.geos import Polygon
from django.db.models import Case
from django.db.models import CharField
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import FloatField
from django.db.models import Func
from django.db.models import OuterRef
from django.db.models import QuerySet
from django.db.models import Subquery
from django.db.models import Value
from django.db.models import When
from django.db.models.lookups import Exact
from django.db.models.lookups import In

from batid.models import Building
from batid.models import City
from batid.models import Plot
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

        qs = qs.filter(point__intersects=poly)
        # We have to order by created_at to avoid pagination issues on geographic queries
        qs = qs.order_by("created_at")

    # #######################
    # Insee Code filter

    insee_code = params.get("insee_code", None)
    if insee_code:
        city = City.objects.get(code_insee=insee_code)
        qs = qs.filter(point__intersects=city.shape)
        # We have to order by created_at to avoid pagination issues on geographic queries
        qs = qs.order_by("created_at")

    cle_interop_ban = params.get("cle_interop_ban", None)
    if cle_interop_ban:
        qs = qs.filter(addresses_read_only__id=cle_interop_ban)
        qs = qs.order_by("created_at")

    # #######################
    # With plots (adding plots ids to the buildings
    with_plots = params.get("with_plots", False)
    if with_plots:

        # Subquery to get the plots ids and the bdg_cover_ratio
        # This quite a big nested query. Here is the breakdwon:
        # - We filter the plots that intersects the building shape
        # - We annotate the bdg_cover_ratio field with the ratio of the building shape that is covered by the plot
        # - We use a Case statement to handle the different geometry types (Point, Polygon)
        # - We use a subquery to get the plots ids and the bdg_cover_ratio
        # - We make an array of them in the "plot" field in the main query (PlotsAggSubquery)
        subquery = (
            Plot.objects.filter(shape__intersects=OuterRef("shape"))
            .annotate(
                bdg_cover_ratio=Case(
                    # When the building shape is a point, the intersecting ratio is 1 (we hard code it since SQL returns 0 instead of 1)
                    When(
                        Exact(
                            Func(OuterRef("shape"), function="ST_GeometryType"),
                            "ST_Point",
                        ),
                        then=Value(1.0),
                    ),
                    # When the building shape is a polygon or a multipolygon, we calculate the intersecting ratio
                    When(
                        In(
                            Func(
                                OuterRef("shape"),
                                function="ST_GeometryType",
                                output_field=CharField(),
                            ),
                            ("ST_Polygon", "ST_MultiPolygon"),
                        ),
                        then=(
                            # This is the formula to calculate the intersecting ratio
                            ExpressionWrapper(
                                (
                                    # We get the area of the intersection between the building shape and the plot shape
                                    Func(
                                        Func(
                                            OuterRef("shape"),
                                            F("shape"),
                                            function="ST_Intersection",
                                        ),
                                        function="ST_Area",
                                        output_field=FloatField(),
                                    )
                                    # We divide it ...
                                    /
                                    # ... by the area of the building shape
                                    Func(
                                        OuterRef("shape"),
                                        function="ST_Area",
                                        output_field=FloatField(),
                                    )
                                ),
                                output_field=FloatField(),
                            )
                        ),
                    ),
                    default=Value(0.0),
                )
            )
            .values("id", "bdg_cover_ratio")
        )
        qs = qs.annotate(plots=PlotsAggSubquery(subquery))

    # to prevent an ugly N+1 problem on the addresses
    qs = qs.prefetch_related("addresses_read_only")

    return qs


class PlotsAggSubquery(Subquery):
    template = "(SELECT json_agg(json_build_object('id', _agg.id, 'bdg_cover_ratio', _agg.bdg_cover_ratio)) FROM (%(subquery)s) _agg)"
