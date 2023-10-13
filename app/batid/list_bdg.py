from django.db.models import QuerySet
from batid.services.bdg_status import BuildingStatus
from batid.models import Building


def public_bdg_queryset(user=None) -> QuerySet:
    allowed_status = BuildingStatus.PUBLIC_TYPES_KEYS

    if user and user.is_authenticated:
        allowed_status = BuildingStatus.ALL_TYPES_KEYS

    return Building.objects.filter(status__type__in=allowed_status).order_by("-rnb_id")


def filter_bdg_queryset(qs: QuerySet, params) -> QuerySet:
    # Status filter
    status = BuildingStatus.DEFAULT_DISPLAY_STATUS

    query_status_str = params.get("status", None)

    if query_status_str:
        if query_status_str == "all":
            status = BuildingStatus.ALL_TYPES_KEYS
        else:
            status = query_status_str.split(",")

    qs = qs.filter(status__type__in=status)

    return qs
