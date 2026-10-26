"""
Summary of the community contributions shown on the home page of the website
(GET /api/alpha/contributions/summary/).

Everything is computed during the request, then cached for an hour: on a
clone of the production data, about 2.5 s for a 30-day window, of which 0.3 s
for the cumulative counts (cities and organizations that ever contributed).
"""

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from batid.models import KPI, Department, SummerChallenge
from batid.services.kpi import (
    KPI_BUILDING_CHANGES_CONTRIBUTIONS,
    KPI_BUILDING_CHANGES_IMPORT_BAL,
    KPI_BUILDING_CHANGES_IMPORT_BDTOPO,
)
from batid.services.RNB_team_user import RNB_TEAM_USERNAME
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import (
    Count,
    F,
    Min,
    QuerySet,
    Sum,
)
from django.utils import timezone

PARIS_TZ = ZoneInfo("Europe/Paris")

# The window is a rolling one, so that the figures do not drop to zero on the
# 1st of the month: the last 7 or 30 days
WINDOWS_DAYS = [7, 30]
DEFAULT_WINDOW_DAYS = 30
TOP_LIMIT = 5
# contributors listed as newcomers
NEWCOMERS_LIMIT = 8

CACHE_KEY = "contribution_summary"
CACHE_TIMEOUT_SECONDS = 3600

# A contribution is one distinct event_id: a single update (eg. shape + address)
# writes several SummerChallenge rows sharing the same event_id
CONTRIBUTIONS = Count("event_id", distinct=True)


def contributions() -> QuerySet:
    """
    SummerChallenge rows of the contributions, the RNB team members counted as
    any other contributor. A row is written for every building change made by
    a user, whatever its origin: imports write rows too, but they all run as
    the technical RNB account, which is left out. This avoids checking the
    origin of each event in the building history, which is far too slow. Data
    fixes write no row (deactivate() only scores contributions).
    """
    return SummerChallenge.objects.exclude(user__username=RNB_TEAM_USERNAME)


def count_contributing() -> dict[str, int]:
    """
    Cities where a contribution was ever made, and organizations whose
    (current) members ever contributed. Two distinct counts over the whole
    history, fast enough for a request (0.3 s on the production data).
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


def _first_time_ids(in_window: QuerySet, field: str, since: datetime) -> set:
    """
    Values of `field` (city_id, user_id…) whose very first contribution is in
    the window. Two indexed queries: the candidates of the window, then those of
    them that contributed before. An anti-join row by row (NOT EXISTS) takes
    minutes for the contributors with a long history.
    """
    candidates = set(
        in_window.exclude(**{f"{field}__isnull": True})
        .values_list(field, flat=True)
        .distinct()
    )
    earlier = set(
        contributions()
        .filter(**{f"{field}__in": candidates}, created_at__lt=since)
        .values_list(field, flat=True)
        .distinct()
    )
    return candidates - earlier


def _building_changes(today: date, days: int) -> dict:
    """
    Building changes of the last `days` complete days, from the daily KPIs
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
            value_date__gte=today - timedelta(days=days),
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
    org_field = "user__profile__organization_id"
    organizations = list(
        in_window.exclude(user__profile__organization__isnull=True)
        .values(org_field, name=F("user__profile__organization__name"))
        .annotate(count=CONTRIBUTIONS)
        .order_by("-count", "name")[:TOP_LIMIT]
    )
    # department of each ranked organization, in one grouped query (a
    # correlated subquery per organization is far slower)
    main_department: dict[int, int] = {}
    for row in (
        in_window.filter(**{f"{org_field}__in": [o[org_field] for o in organizations]})
        .exclude(department__isnull=True)
        .values(org_field, "department_id")
        .annotate(count=CONTRIBUTIONS)
        .order_by(org_field, "-count", "department_id")
    ):
        main_department.setdefault(row[org_field], row["department_id"])
    departments = _departments(set(main_department.values()))
    return [
        {
            "name": o["name"],
            "department": departments.get(main_department.get(o[org_field], 0)),
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


def compute_contribution_summary(
    now: Optional[datetime] = None, days: int = DEFAULT_WINDOW_DAYS
) -> dict:
    """See the GET /api/alpha/contributions/summary/ documentation for the format"""
    now = (now or timezone.now()).astimezone(PARIS_TZ)
    since = now - timedelta(days=days)
    in_window = contributions().filter(created_at__gte=since, created_at__lt=now)

    contributing = count_contributing()
    new_city_ids = _first_time_ids(in_window, "city_id", since)
    new_user_ids = _first_time_ids(in_window, "user_id", since)
    new_organizations = len(
        _first_time_ids(in_window, "user__profile__organization_id", since)
    )
    # the latest first contributions first
    new_users = list(
        in_window.filter(user_id__in=new_user_ids)
        .values("user_id", username=F("user__username"))
        .annotate(first_contribution_at=Min("created_at"))
        .order_by("-first_contribution_at")[:NEWCOMERS_LIMIT]
    )

    return {
        "updated_at": now.isoformat(),
        "window_days": days,
        "cities": {
            "total": contributing["cities"],
            "new": len(new_city_ids),
        },
        "organizations": {
            "total": contributing["organizations"],
            "new": new_organizations,
        },
        # the window itself, and the contributions of the window of the same
        # length just before, to show a trend
        "activity": {
            **in_window.aggregate(
                contributions=CONTRIBUTIONS,
                cities=Count("city", distinct=True),
                contributors=Count("user", distinct=True),
            ),
            "new_contributors": len(new_user_ids),
            "previous_contributions": contributions()
            .filter(
                created_at__gte=since - timedelta(days=days),
                created_at__lt=since,
            )
            .aggregate(n=CONTRIBUTIONS)["n"],
        },
        "building_changes": _building_changes(now.date(), days),
        "top": {
            "users": _top_users(in_window),
            "organizations": _top_organizations(in_window),
            "cities": _top_cities(in_window),
        },
        # contributors whose very first contribution is in the window, the
        # latest first
        "newcomers": {
            "users": [{"username": public_username(u["username"])} for u in new_users],
        },
    }


def get_contribution_summary(days: int = DEFAULT_WINDOW_DAYS) -> dict:
    """Cached version of compute_contribution_summary"""
    key = f"{CACHE_KEY}:{days}"
    data = cache.get(key)
    if data is None:
        data = compute_contribution_summary(days=days)
        cache.set(key, data, CACHE_TIMEOUT_SECONDS)
    return data
