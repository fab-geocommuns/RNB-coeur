from typing import Optional
from datetime import date

from batid.services.bdg_status import BuildingStatus
from batid.models import KPI
from batid.models import Building

KPI_ACTIVE_BUILDINGS_COUNT = "active_buildings_count"
KPI_REAL_BUILDINGS_COUNT = "real_buildings_count"


def get_kpi(name: str, since: Optional[date] = None, until: Optional[date] = None):

    qs = KPI.objects.filter(name=name)
    if since:
        qs = qs.filter(value_date__gte=since)
    if until:
        qs = qs.filter(value_date__lte=until)

    return qs


def get_kpi_most_recent(name: str):

    return KPI.objects.filter(name=name).last()


def compute_today_kpis():

    today = date.today()

    # Active buildings
    active_bdgs_count = compute_active_buildings_count()
    KPI.objects.create(
        name=KPI_ACTIVE_BUILDINGS_COUNT, value=active_bdgs_count, value_date=today
    )

    # Real buildings
    real_bdgs_count = compute_real_buildings_count()
    KPI.objects.create(
        name=KPI_REAL_BUILDINGS_COUNT, value=real_bdgs_count, value_date=today
    )


def compute_active_buildings_count():
    """
    Count the number of active buildings
    """

    return Building.objects.filter(is_active=True).count()


def compute_real_buildings_count():
    """
    Count the number of real (active + physical status) buildings
    """

    return Building.objects.filter(
        is_active=True, status__in=BuildingStatus.REAL_BUILDINGS_STATUS
    ).count()
