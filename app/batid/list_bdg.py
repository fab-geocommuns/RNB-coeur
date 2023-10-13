from django.db.models import QuerySet
from batid.services.bdg_status import BuildingStatus
from batid.models import Building


def public_bdg_queryset(user=None) -> QuerySet:
    allowed_status = BuildingStatus.PUBLIC_TYPES_KEYS

    if user and user.is_authenticated:
        allowed_status = BuildingStatus.ALL_TYPES_KEYS

    return Building.objects.filter(status__type__in=allowed_status)
