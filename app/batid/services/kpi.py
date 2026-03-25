from datetime import date
from datetime import timedelta
from typing import Optional

import requests
from django.db import connection
from rest_framework_tracking.models import APIRequestLog

from batid.models import Building
from batid.models import Contribution
from batid.models import KPI
from batid.models.report import Report
from batid.services.bdg_status import BuildingStatus

KPI_ACTIVE_BUILDINGS_COUNT = "active_buildings_count"
KPI_REAL_BUILDINGS_COUNT = "real_buildings_count"
KPI_REAL_BUILDINGS_WO_ADDRESSES_COUNT = "real_buildings_wo_addresses_count"
KPI_BUILDING_ADDRESS_COUNT = "building_address_links_count"
KPI_EDITORS_COUNT = "editors_count"
KPI_EDITS_COUNT = "edits_count"
KPI_REPORTS_COUNT = "reports_count"
KPI_PENDING_REPORTS_COUNT = "pending_reports_count"
KPI_FIXED_REPORTS_COUNT = "fixed_reports_count"
KPI_REFUSED_REPORTS_COUNT = "refused_reports_count"
KPI_EDITS_COUNT_BY_DEPT = "edits_count_by_dept_{}"
KPI_API_REQUESTS_COUNT = "api_requests_count"
KPI_DATA_GOUV_VIEWS = "data_gouv_views_count"
KPI_DATA_GOUV_DOWNLOADS = "data_gouv_downloads_count"


def get_kpi(name: str, since: Optional[date] = None, until: Optional[date] = None):

    qs = KPI.objects.filter(name=name)
    if since:
        qs = qs.filter(value_date__gte=since)
    if until:
        qs = qs.filter(value_date__lte=until)

    return qs


def get_kpi_most_recent(name: str):

    return KPI.objects.filter(name=name).last()


def compute_today_kpis(external_calls=True):
    """
    external_calls=False is for testing purposes, to avoid creating a Mock
    """

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

    # Building - address links
    building_address_links_count = count_building_address_links()
    KPI.objects.create(
        name=KPI_BUILDING_ADDRESS_COUNT,
        value=building_address_links_count,
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

    # API requests
    api_requests_count = count_api_requests()
    KPI.objects.create(
        name=KPI_API_REQUESTS_COUNT, value=api_requests_count, value_date=today
    )

    # Edits by department
    for dept_code, count in count_edits_by_department().items():
        KPI.objects.update_or_create(
            name=KPI_EDITS_COUNT_BY_DEPT.format(dept_code),
            defaults={"value": count, "value_date": today},
        )

    # data.gouv stats
    if external_calls:
        (views_count, downloads_count) = get_data_gouv_stats()
        if views_count is not None:
            KPI.objects.create(
                name=KPI_DATA_GOUV_VIEWS, value=views_count, value_date=today
            )
        if downloads_count is not None:
            KPI.objects.create(
                name=KPI_DATA_GOUV_DOWNLOADS,
                value=downloads_count,
                value_date=today,
            )


def get_data_gouv_stats() -> tuple:
    """
    fetch some stats on the data.gouv API
    """
    resp = requests.get(
        "https://www.data.gouv.fr/api/1/datasets/referentiel-national-des-batiments/"
    )

    if resp.status_code == 200:
        data = resp.json()
        views_count = data.get("metrics", {}).get("views")
        downloads_count = data.get("metrics", {}).get("resources_downloads", None)
        return (views_count, downloads_count)
    else:
        return (None, None)


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


def count_building_address_links():
    """
    Count the number of building - address links
    """
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = 30000;")
        cursor.execute(
            "SELECT COUNT(*) FROM batid_buildingaddressesreadonly ba"
            " JOIN batid_building b ON ba.building_id = b.id"
            " WHERE b.is_active = TRUE"
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def count_editors():
    return Contribution.objects.filter(report=False).distinct("review_user_id").count()


def count_edits():
    return Contribution.objects.filter(report=False).count()


def count_reports():
    return Report.objects.count()


def count_pending_reports():
    return Report.objects.filter(status="pending").count()


def count_fixed_reports():
    return Report.objects.filter(status="fixed").count()


def count_refused_reports():
    return Report.objects.filter(status="rejected").count()


def count_api_requests():
    """
    Count the total number of API requests logged in rest_framework_tracking_apirequestlog
    """
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = 30000;")
        cursor.execute("SELECT COUNT(*) FROM rest_framework_tracking_apirequestlog")
        row = cursor.fetchone()
        return row[0] if row else 0


def backfill_api_requests_kpi():
    """
    One-shot function to backfill api_requests_count KPI, one cumulative value per month,
    from the first recorded API request until the previous month (current month excluded).
    Skips months that already have an entry.
    """
    first = (
        APIRequestLog.objects.order_by("requested_at")
        .values_list("requested_at", flat=True)
        .first()
    )
    if not first:
        return

    today = date.today()
    year, month = first.year, first.month

    while (year, month) < (today.year, today.month):
        # Last day of this month
        if month == 12:
            next_first = date(year + 1, 1, 1)
        else:
            next_first = date(year, month + 1, 1)
        last_day = next_first - timedelta(days=1)

        count = APIRequestLog.objects.filter(requested_at__date__lte=last_day).count()
        KPI.objects.get_or_create(
            name=KPI_API_REQUESTS_COUNT,
            value_date=last_day,
            defaults={"value": count},
        )

        year, month = next_first.year, next_first.month


def count_edits_by_department():
    """
    Count contributions (edits, not reports) per department using a spatial join.
    Returns a dict {dept_code: count}.
    """
    sql = """
        SELECT d.code, COUNT(*) AS count
        FROM batid_contribution c
            INNER JOIN batid_building b ON c.rnb_id = b.rnb_id
            LEFT JOIN batid_department_subdivided d ON ST_Contains(d.shape, b.point)
        WHERE c.report = false
        GROUP BY d.code
    """
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return {row[0]: row[1] for row in cursor.fetchall()}
