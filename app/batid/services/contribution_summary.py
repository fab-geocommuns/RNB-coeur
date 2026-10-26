"""
Summary of the community contributions shown on the home page of the website
(GET /api/alpha/contributions/summary/).

- The cumulative counts (cities and organizations that ever contributed) read
  the whole history: they are daily KPIs, computed every night by
  compute_daily_kpis.
- Everything about the last WINDOW_DAYS days is computed during the request,
  then cached for an hour (about 2 s on a busy window of the staging data).
"""

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from batid.models import KPI, Department, SummerChallenge
from batid.services.kpi import (
    KPI_BUILDING_CHANGES_CONTRIBUTIONS,
    KPI_BUILDING_CHANGES_IMPORT_BAL,
    KPI_BUILDING_CHANGES_IMPORT_BDTOPO,
    KPI_CONTRIBUTING_CITIES_COUNT,
    KPI_CONTRIBUTING_ORGANIZATIONS_COUNT,
    get_kpi_most_recent,
)
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import (
    Count,
    Exists,
    F,
    Min,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
)
from django.utils import timezone

PARIS_TZ = ZoneInfo("Europe/Paris")

# "This month" on the home page is a rolling window of 30 days, so that the
# figures do not drop to zero on the 1st of the month
WINDOW_DAYS = 30
TOP_LIMIT = 5
NEW_CITIES_LIMIT = 8

CACHE_KEY = "contribution_summary"
CACHE_TIMEOUT_SECONDS = 3600

# A contribution is one distinct event_id: a single update (eg. shape + address)
# writes several SummerChallenge rows sharing the same event_id
CONTRIBUTIONS = Count("event_id", distinct=True)


def contributions() -> QuerySet:
    """
    SummerChallenge rows of the community contributions. A row is written for
    every building change made by a user, whatever its origin: imports and data
    fixes write rows too, but they are run as the RNB team user. Leaving out
    the RNB team (its organization, and the staff accounts which all belong to
    it) leaves them out as well, without checking the origin of each event in
    the building history, which is far too slow.
    """
    return SummerChallenge.objects.exclude(
        Q(user__is_staff=True)
        | Q(user__is_superuser=True)
        | Q(user__profile__organization__name=settings.RNB_TEAM_ORG_NAME)
    )


def count_contributing() -> dict[str, int]:
    """
    Cities where a contribution was ever made, and organizations whose
    (current) members ever contributed. Reads the whole history: computed
    every night as KPIs, not during a request.
    """
    editions = contributions()
    return {
        "cities": editions.exclude(city__isnull=True)
        .values("city_id")
        .distinct()
        .count(),
        "organizations": editions.exclude(user__profile__organization__isnull=True)
        .values("user__profile__organization_id")
        .distinct()
        .count(),
    }


def public_username(username: str) -> str:
    """Some usernames are email addresses: only their local part is shown"""
    return username.split("@")[0]


def _departments(ids: set[Optional[int]]) -> dict[int, dict]:
    """{"code", "name"} of departments, by id"""
    return {
        d["id"]: {"code": d["code"], "name": d["name"]}
        for d in Department.objects.filter(id__in=[i for i in ids if i]).values(
            "id", "code", "name"
        )
    }


def _city_rows(editions: QuerySet) -> QuerySet:
    """
    Editions grouped by city. A city is grouped alone (not with its department) so
    that rows whose department could not be resolved do not split it in two: its
    department is taken from its rows.
    """
    return (
        editions.exclude(city__isnull=True)
        .values("city_id", insee_code=F("city__code_insee"), name=F("city__name"))
        .annotate(department_ref=Min("department"))
    )


def _first_time(rows: QuerySet, group_field: str, since: datetime) -> QuerySet:
    """
    rows are the window's contributions grouped by group_field: keeps the groups
    with no contribution before the window, ie. whose very first one is in it.
    Candidates come from the window only, so the whole history is never grouped.
    """
    earlier = contributions().filter(
        **{group_field: OuterRef(group_field)}, created_at__lt=since
    )
    return rows.filter(~Exists(earlier))


def _total(kpi_name: str) -> Optional[int]:
    """Latest value of a nightly KPI, None before its first computation"""
    kpi = get_kpi_most_recent(kpi_name)
    return int(kpi.value) if kpi else None


def _building_changes(today: date) -> dict:
    """
    Building changes of the last WINDOW_DAYS complete days, from the daily KPIs
    (computed every night for the day before): a building changed twice counts
    twice. The contributions include the RNB team ones, the KPIs do not split them.
    """
    sums = {
        row["name"]: row["value"]
        for row in KPI.objects.filter(
            name__in=[
                KPI_BUILDING_CHANGES_IMPORT_BDTOPO,
                KPI_BUILDING_CHANGES_IMPORT_BAL,
                KPI_BUILDING_CHANGES_CONTRIBUTIONS,
            ],
            value_date__gte=today - timedelta(days=WINDOW_DAYS),
            value_date__lt=today,
        )
        .values("name")
        .annotate(value=Sum("value"))
    }
    return {
        "total": int(sum(sums.values())),
        "contributions": int(sums.get(KPI_BUILDING_CHANGES_CONTRIBUTIONS, 0)),
    }


def _top_users(in_window: QuerySet) -> list[dict]:
    users = list(
        in_window.values("user_id", username=F("user__username"))
        .annotate(count=CONTRIBUTIONS)
        .order_by("-count", "username")[:TOP_LIMIT]
    )
    organizations = {
        u["id"]: u["profile__organization__short_name"]
        or u["profile__organization__name"]
        for u in User.objects.filter(id__in=[u["user_id"] for u in users]).values(
            "id", "profile__organization__short_name", "profile__organization__name"
        )
    }
    return [
        {
            "username": public_username(u["username"]),
            "organization": organizations.get(u["user_id"]),
            "count": u["count"],
        }
        for u in users
    ]


def _top_organizations(in_window: QuerySet) -> list[dict]:
    """
    Organizations ranked by the contributions of their current members. An
    organization has no department: the one where it contributed the most in the
    window is shown.
    """
    main_department = (
        in_window.filter(
            user__profile__organization_id=OuterRef("user__profile__organization_id")
        )
        .exclude(department__isnull=True)
        .values("department_id")
        .annotate(count=CONTRIBUTIONS)
        .order_by("-count", "department_id")
        .values("department_id")[:1]
    )
    organizations = list(
        in_window.exclude(user__profile__organization__isnull=True)
        .values(
            "user__profile__organization_id",
            name=F("user__profile__organization__name"),
        )
        .annotate(count=CONTRIBUTIONS, department_ref=Subquery(main_department))
        .order_by("-count", "name")[:TOP_LIMIT]
    )
    departments = _departments({o["department_ref"] for o in organizations})
    return [
        {
            "name": o["name"],
            "department": departments.get(o["department_ref"]),
            "count": o["count"],
        }
        for o in organizations
    ]


def _city(row: dict, departments: dict[int, dict]) -> dict:
    return {
        "insee_code": row["insee_code"],
        "name": row["name"],
        "department": departments.get(row["department_ref"]),
    }


def _top_cities(in_window: QuerySet) -> list[dict]:
    cities = list(
        _city_rows(in_window)
        .annotate(count=CONTRIBUTIONS)
        .order_by("-count", "name")[:TOP_LIMIT]
    )
    departments = _departments({c["department_ref"] for c in cities})
    return [{**_city(c, departments), "count": c["count"]} for c in cities]


def compute_contribution_summary(now: Optional[datetime] = None) -> dict:
    """See the GET /api/alpha/contributions/summary/ documentation for the format"""
    now = (now or timezone.now()).astimezone(PARIS_TZ)
    since = now - timedelta(days=WINDOW_DAYS)
    in_window = contributions().filter(created_at__gte=since, created_at__lt=now)

    # few cities contribute for the first time in a window: all fetched, to
    # count them in the same query
    new_cities = list(
        _first_time(_city_rows(in_window), "city_id", since)
        .annotate(first_contribution_at=Min("created_at"))
        .order_by("-first_contribution_at")
    )
    new_cities_departments = _departments({c["department_ref"] for c in new_cities})
    new_organizations = _first_time(
        in_window.exclude(user__profile__organization__isnull=True)
        .values("user__profile__organization_id")
        .distinct(),
        "user__profile__organization_id",
        since,
    ).count()

    return {
        "updated_at": now.isoformat(),
        "window_days": WINDOW_DAYS,
        # total: None until the nightly KPIs are computed for the first time
        "cities": {
            "total": _total(KPI_CONTRIBUTING_CITIES_COUNT),
            "new": len(new_cities),
        },
        "organizations": {
            "total": _total(KPI_CONTRIBUTING_ORGANIZATIONS_COUNT),
            "new": new_organizations,
        },
        "building_changes": _building_changes(now.date()),
        "top": {
            "users": _top_users(in_window),
            "organizations": _top_organizations(in_window),
            "cities": _top_cities(in_window),
        },
        "new_cities": [
            _city(c, new_cities_departments) for c in new_cities[:NEW_CITIES_LIMIT]
        ],
    }


def get_contribution_summary() -> dict:
    """Cached version of compute_contribution_summary"""
    data = cache.get(CACHE_KEY)
    if data is None:
        data = compute_contribution_summary()
        cache.set(CACHE_KEY, data, CACHE_TIMEOUT_SECONDS)
    return data
