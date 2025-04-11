from typing import Optional
from datetime import date

from batid.services.bdg_status import BuildingStatus
from batid.models import KPI, Contribution
from batid.models import Building

KPI_ACTIVE_BUILDINGS_COUNT = "active_buildings_count"
KPI_REAL_BUILDINGS_COUNT = "real_buildings_count"
KPI_REAL_BUILDINGS_WO_ADDRESSES_COUNT = "real_buildings_wo_addresses_count"
KPI_EDITORS_COUNT = "editors_count"
KPI_EDITS_COUNT = "edits_count"
KPI_REPORTS_COUNT = "reports_count"
KPI_PENDING_REPORTS_COUNT = "pending_reports_count"
KPI_FIXED_REPORTS_COUNT = "fixed_reports_count"
KPI_REFUSED_REPORTS_COUNT = "refused_reports_count"


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
    active_bdgs_count = count_active_buildings()
    KPI.objects.create(
        name=KPI_ACTIVE_BUILDINGS_COUNT, value=active_bdgs_count, value_date=today
    )

    # Real buildings
    real_bdgs_count = count_real_buildings()
    KPI.objects.create(
        name=KPI_REAL_BUILDINGS_COUNT, value=real_bdgs_count, value_date=today
    )

    # Real buildings without addresses
    real_bdgs_wo_addresses_count = count_real_buildings_wo_addresses()
    KPI.objects.create(
        name=KPI_REAL_BUILDINGS_WO_ADDRESSES_COUNT,
        value=real_bdgs_wo_addresses_count,
        value_date=today,
    )

    # Editors
    editors_count = count_editors()
    KPI.objects.create(name=KPI_EDITORS_COUNT, value=editors_count, value_date=today)

    # Edits
    edits_count = count_edits()
    KPI.objects.create(name=KPI_EDITS_COUNT, value=edits_count, value_date=today)

    # Reports
    reports_count = count_reports()
    KPI.objects.create(name=KPI_REPORTS_COUNT, value=reports_count, value_date=today)

    # Pending reports
    pending_reports_count = count_pending_reports()
    KPI.objects.create(
        name=KPI_PENDING_REPORTS_COUNT,
        value=pending_reports_count,
        value_date=today,
    )

    # Fixed reports
    fixed_reports_count = count_fixed_reports()
    KPI.objects.create(
        name=KPI_FIXED_REPORTS_COUNT, value=fixed_reports_count, value_date=today
    )

    # Refused reports
    refused_reports_count = count_refused_reports()
    KPI.objects.create(
        name=KPI_REFUSED_REPORTS_COUNT, value=refused_reports_count, value_date=today
    )


def count_active_buildings():
    """
    Count the number of active buildings
    """

    return Building.objects.filter(is_active=True).count()


def count_real_buildings():
    """
    Count the number of real (active + physical status) buildings
    """

    return Building.objects.filter(
        is_active=True, status__in=BuildingStatus.REAL_BUILDINGS_STATUS
    ).count()


def count_real_buildings_wo_addresses():
    """
    Count the number of real (active + physical status) buildings without addresses
    """

    return Building.objects.filter(
        is_active=True,
        status__in=BuildingStatus.REAL_BUILDINGS_STATUS,
        addresses_read_only=None,
    ).count()


def count_editors():
    return Contribution.objects.filter(report=False).distinct("review_user_id").count()


def count_edits():
    return Contribution.objects.filter(report=False).count()


def count_reports():
    return Contribution.objects.filter(report=True).count()


def count_pending_reports():
    return Contribution.objects.filter(report=True, status="pending").count()


def count_fixed_reports():
    return Contribution.objects.filter(report=True, status="fixed").count()


def count_refused_reports():
    return Contribution.objects.filter(report=True, status="refused").count()
