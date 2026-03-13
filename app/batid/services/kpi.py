from datetime import date
from datetime import timedelta
from typing import Optional

from django.db import connection

from batid.models import Building
from batid.models import Contribution
from batid.models import KPI
from batid.models.report import Report
from batid.services.bdg_status import BuildingStatus

KPI_ACTIVE_BUILDINGS_COUNT = "active_buildings_count"
KPI_REAL_BUILDINGS_COUNT = "real_buildings_count"
KPI_REAL_BUILDINGS_WO_ADDRESSES_COUNT = "real_buildings_wo_addresses_count"
KPI_EDITORS_COUNT = "editors_count"
KPI_EDITS_COUNT = "edits_count"
KPI_REPORTS_COUNT = "reports_count"
KPI_PENDING_REPORTS_COUNT = "pending_reports_count"
KPI_FIXED_REPORTS_COUNT = "fixed_reports_count"
KPI_REFUSED_REPORTS_COUNT = "refused_reports_count"

KPI_BUILDING_CHANGES_IMPORT_BDTOPO = "building_changes_import_bdtopo"
KPI_BUILDING_CHANGES_IMPORT_BAL = "building_changes_import_bal"
KPI_BUILDING_CHANGES_CONTRIBUTIONS = "building_changes_contributions"


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

    # Building change stats (import_bdtopo, import_bal, contributions)
    bdtopo_count = count_building_changes_import_bdtopo(today)
    KPI.objects.create(
        name=KPI_BUILDING_CHANGES_IMPORT_BDTOPO, value=bdtopo_count, value_date=today
    )
    bal_count = count_building_changes_import_bal(today)
    KPI.objects.create(
        name=KPI_BUILDING_CHANGES_IMPORT_BAL, value=bal_count, value_date=today
    )
    contributions_count = count_building_changes_contributions(today)
    KPI.objects.create(
        name=KPI_BUILDING_CHANGES_CONTRIBUTIONS,value=contributions_count, value_date=today,
    )


def _count_building_changes_import(for_date: date, import_source: str) -> int:
    """Nombre de lignes dans la vue (event_origin=import + BuildingImport.import_source=...) à la date for_date."""
    sql = """
        SELECT COUNT(*) FROM batid_building_with_history b
        JOIN batid_buildingimport bi ON bi.id = (b.event_origin->>'id')::int
        WHERE b.event_origin->>'source' = 'import'
        AND bi.import_source = %s
        AND (lower(b.sys_period))::date = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [import_source, for_date])
        row = cursor.fetchone()
    return row[0] if row else 0


def count_building_changes_import_bdtopo(for_date: date) -> int:
    """Nombre de lignes dans la vue (event_origin=import + BuildingImport.import_source=bdtopo) à la date for_date."""
    return _count_building_changes_import(for_date, "bdtopo")


def count_building_changes_import_bal(for_date: date) -> int:
    """Nombre de lignes dans la vue (event_origin=import + BuildingImport.import_source=bal) à la date for_date."""
    return _count_building_changes_import(for_date, "bal")


def count_building_changes_contributions(for_date: date) -> int:
    """Nombre de lignes dans la vue (event_origin.source=contribution) à la date for_date."""
    sql = """
        SELECT COUNT(*) FROM batid_building_with_history
        WHERE event_origin->>'source' = 'contribution'
        AND (lower(sys_period))::date = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [for_date])
        row = cursor.fetchone()
    return row[0] if row else 0


def get_building_change_stats(since: date, until: date) -> list[dict]:
    """Liste des stats par jour entre since et until. Chaque élément : date (ISO), events_count (import_bdtopo, import_bal, contributions)."""
    qs_bdtopo = get_kpi(KPI_BUILDING_CHANGES_IMPORT_BDTOPO, since=since, until=until)
    qs_bal = get_kpi(KPI_BUILDING_CHANGES_IMPORT_BAL, since=since, until=until)
    qs_contrib = get_kpi(KPI_BUILDING_CHANGES_CONTRIBUTIONS, since=since, until=until)

    by_date = {}
    for k in qs_bdtopo:
        by_date.setdefault(
            k.value_date,
            {"import_bdtopo": 0, "import_bal": 0, "contributions": 0},
        )
        by_date[k.value_date]["import_bdtopo"] = int(k.value)
    for k in qs_bal:
        by_date.setdefault(
            k.value_date,
            {"import_bdtopo": 0, "import_bal": 0, "contributions": 0},
        )
        by_date[k.value_date]["import_bal"] = int(k.value)
    for k in qs_contrib:
        by_date.setdefault(
            k.value_date,
            {"import_bdtopo": 0, "import_bal": 0, "contributions": 0},
        )
        by_date[k.value_date]["contributions"] = int(k.value)

    out = []
    d = since
    # Jours sans KPI (ex. calcul nocturne non exécuté) : on renvoie 0 par défaut. je ne sais pas trop si il faut mettre un null ou un 0 par defaut
    while d <= until:
        events = by_date.get(
            d, {"import_bdtopo": 0, "import_bal": 0, "contributions": 0}
        )
        out.append({"date": d.isoformat(), "events_count": events})
        d += timedelta(days=1)
    return out


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
    return Report.objects.count()


def count_pending_reports():
    return Report.objects.filter(status="pending").count()


def count_fixed_reports():
    return Report.objects.filter(status="fixed").count()


def count_refused_reports():
    return Report.objects.filter(status="rejected").count()
