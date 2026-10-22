from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from batid.models import BuildingWithHistory, Department, SummerChallenge
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Count, Exists, F, Min, OuterRef, QuerySet
from django.db.models.fields.json import KT
from django.db.models.functions import TruncMonth
from django.utils import timezone

# The months of the monthly series are calendar months in the French
# metropolitan timezone
PARIS_TZ = ZoneInfo("Europe/Paris")

# A period is either a rolling window of the last N days, or the whole history
DEFAULT_DAYS = 30
MAX_DAYS = 365
PERIOD_ALL = "all"

DEFAULT_LIMIT = 5
MAX_LIMIT = 20

CACHE_TIMEOUT_SECONDS = 600

# number of months returned in the monthly series
MONTHLY_SERIES_LENGTH = 12

# A contribution is one distinct event_id: a single update (eg. shape + address)
# writes several SummerChallenge rows sharing the same event_id
CONTRIBUTIONS = Count("event_id", distinct=True)


def contributions() -> QuerySet:
    """
    SummerChallenge rows made by contributors. Imports (candidate.py) and data fixes
    also write rows in SummerChallenge, mostly with the RNB team user: they are
    excluded by keeping only the events whose origin is a contribution.
    The RNB team and staff accounts are counted as any other user.
    """
    contribution_events = BuildingWithHistory.objects.annotate(
        origin_source=KT("event_origin__source")
    ).filter(event_id=OuterRef("event_id"), origin_source="contribution")
    return SummerChallenge.objects.filter(Exists(contribution_events))


def period_key(days: Optional[int]) -> str:
    """ "last_30_days" for a rolling window, "all" for the whole history"""
    return f"last_{days}_days" if days else PERIOD_ALL


def _filter_dates(
    qs: QuerySet, field: str, since: Optional[datetime], until: Optional[datetime]
) -> QuerySet:
    if since:
        qs = qs.filter(**{f"{field}__gte": since})
    if until:
        qs = qs.filter(**{f"{field}__lt": until})
    return qs


def _with_dense_rank(rows: list[dict]) -> list[dict]:
    """rows are sorted by count desc; equal counts share the same rank (1, 1, 2...)"""
    rank = 0
    previous_count = None
    for row in rows:
        if row["count"] != previous_count:
            rank += 1
            previous_count = row["count"]
        row["rank"] = rank
    return rows


def _departments(rows: list[dict]) -> dict[int, dict]:
    """{"code", "name"} of the departments referenced by the department_ref of rows"""
    ids = {r["department_ref"] for r in rows if r["department_ref"]}
    return {
        d["id"]: {"code": d["code"], "name": d["name"]}
        for d in Department.objects.filter(id__in=ids).values("id", "code", "name")
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


def _organization_short_names(user_ids: list[int]) -> dict[int, Optional[str]]:
    """Current organization of each user: its short name, or its name if it has none"""
    users = User.objects.filter(id__in=user_ids).values(
        "id", "profile__organization__short_name", "profile__organization__name"
    )
    return {
        u["id"]: u["profile__organization__short_name"]
        or u["profile__organization__name"]
        for u in users
    }


def _top(qs: QuerySet, limit: int) -> dict[str, list[dict]]:
    """Rankings of the contributions of qs"""

    users = list(
        qs.values("user_id", username=F("user__username"))
        .annotate(count=CONTRIBUTIONS)
        .order_by("-count", "username")[:limit]
    )
    org_names = _organization_short_names([u["user_id"] for u in users])
    users = [
        {
            "username": u["username"],
            "organization_short_name": org_names.get(u["user_id"]),
            "count": u["count"],
        }
        for u in users
    ]

    # current organization of the users
    organizations = [
        {"name": o["name"], "short_name": o["short_name"], "count": o["count"]}
        for o in qs.exclude(user__profile__organization__isnull=True)
        .values(
            "user__profile__organization_id",
            name=F("user__profile__organization__name"),
            short_name=F("user__profile__organization__short_name"),
        )
        .annotate(count=CONTRIBUTIONS)
        .order_by("-count", "name")[:limit]
    ]

    cities = list(
        _city_rows(qs).annotate(count=CONTRIBUTIONS).order_by("-count", "name")[:limit]
    )
    departments_by_id = _departments(cities)
    cities = [
        {
            "insee_code": c["insee_code"],
            "name": c["name"],
            "department": departments_by_id.get(c["department_ref"]),
            "count": c["count"],
        }
        for c in cities
    ]

    departments = list(
        qs.exclude(department__isnull=True)
        .values(code=F("department__code"), name=F("department__name"))
        .annotate(count=CONTRIBUTIONS)
        .order_by("-count", "code")[:limit]
    )

    return {
        "users": _with_dense_rank(users),
        "organizations": _with_dense_rank(organizations),
        "cities": _with_dense_rank(cities),
        "departments": _with_dense_rank(departments),
    }


def _newcomers(editions: QuerySet, since: datetime, limit: int) -> dict:
    """
    Users, cities and departments whose very first contribution is in the period,
    the most recent first.
    Candidates are taken among the period's editions only, then those having a
    contribution before the period are excluded: computing the first edition of
    every user, city and department over the whole history is far too slow.
    """

    counts = {}
    in_period = editions.filter(created_at__gte=since)

    def first_editions(key: str, rows: QuerySet, group_field: str) -> list[dict]:
        earlier = editions.filter(
            **{group_field: OuterRef(group_field)}, created_at__lt=since
        )
        # few candidates in a period: fetch them all to count them in one query
        firsts = list(
            rows.filter(~Exists(earlier))
            .annotate(first_edition_at=Min("created_at"))
            .order_by("-first_edition_at")
        )
        counts[key] = len(firsts)
        return firsts[:limit]

    users = first_editions(
        "users", in_period.values("user_id", username=F("user__username")), "user_id"
    )
    org_names = _organization_short_names([u["user_id"] for u in users])

    cities = first_editions("cities", _city_rows(in_period), "city_id")
    departments_by_id = _departments(cities)

    departments = first_editions(
        "departments",
        in_period.exclude(department__isnull=True).values(
            "department_id", code=F("department__code"), name=F("department__name")
        ),
        "department_id",
    )

    return {
        "users": [
            {
                "username": u["username"],
                "organization_short_name": org_names.get(u["user_id"]),
                "first_edition_at": u["first_edition_at"]
                .astimezone(PARIS_TZ)
                .isoformat(),
            }
            for u in users
        ],
        "cities": [
            {
                "insee_code": c["insee_code"],
                "name": c["name"],
                "department": departments_by_id.get(c["department_ref"]),
                "first_edition_at": c["first_edition_at"]
                .astimezone(PARIS_TZ)
                .isoformat(),
            }
            for c in cities
        ],
        "departments": [
            {
                "code": d["code"],
                "name": d["name"],
                "first_edition_at": d["first_edition_at"]
                .astimezone(PARIS_TZ)
                .isoformat(),
            }
            for d in departments
        ],
        # total numbers of newcomers, the lists above being limited
        "count": counts,
    }


def _add_months(month_start: datetime, months: int) -> datetime:
    """First day of the month, `months` months after (or before) month_start"""
    index = month_start.year * 12 + month_start.month - 1 + months
    return datetime(index // 12, index % 12 + 1, 1, tzinfo=PARIS_TZ)


def _monthly_editions(editions: QuerySet, now: datetime) -> list[dict]:
    """Number of editions of each of the last MONTHLY_SERIES_LENGTH months, current one included"""
    current_month = datetime(now.year, now.month, 1, tzinfo=PARIS_TZ)
    first_month = _add_months(current_month, -(MONTHLY_SERIES_LENGTH - 1))

    rows = (
        editions.filter(created_at__gte=first_month)
        .annotate(month=TruncMonth("created_at", tzinfo=PARIS_TZ))
        .values("month")
        .annotate(count=CONTRIBUTIONS)
    )
    by_month = {row["month"].strftime("%Y-%m"): row["count"] for row in rows}

    months = [
        _add_months(first_month, i).strftime("%Y-%m")
        for i in range(MONTHLY_SERIES_LENGTH)
    ]
    return [{"month": m, "editions": by_month.get(m, 0)} for m in months]


def _previous_period(editions: QuerySet, days: int, now: datetime) -> dict:
    """Number of editions of the `days` days before the window, to show a trend"""
    until = now - timedelta(days=days)
    since = until - timedelta(days=days)
    count = _filter_dates(editions, "created_at", since, until).aggregate(
        editions=CONTRIBUTIONS
    )["editions"]
    return {
        "since": since.date().isoformat(),
        "until": until.isoformat(),
        "editions": count,
    }


def _date_or_none(dt: Optional[datetime]) -> Optional[str]:
    return dt.date().isoformat() if dt else None


def compute_edition_activity(
    days: Optional[int] = DEFAULT_DAYS,
    limit: int = DEFAULT_LIMIT,
    now: Optional[datetime] = None,
) -> dict:
    """
    Contribution statistics of the last `days` days (whole history when days is
    None), computed from the SummerChallenge table: totals, rankings (users,
    organizations, cities, departments) and newcomers.
    See the GET /api/alpha/editions/activity/ documentation for the output format.
    """
    now = (now or timezone.now()).astimezone(PARIS_TZ)
    since = now - timedelta(days=days) if days else None
    editions = contributions()
    in_period = _filter_dates(editions, "created_at", since, None)

    totals = in_period.aggregate(
        editions=CONTRIBUTIONS,
        cities=Count("city", distinct=True),
        editors=Count("user", distinct=True),
    )

    newcomers: dict
    if since:
        newcomers = _newcomers(editions, since, limit)
    else:
        # everybody is a newcomer of the whole history
        newcomers = {"users": [], "cities": [], "departments": [], "count": None}

    return {
        "period": {"key": period_key(days), "since": _date_or_none(since)},
        "updated_at": timezone.now().astimezone(PARIS_TZ).isoformat(),
        "totals": totals,
        "previous_period": _previous_period(editions, days, now) if days else None,
        "monthly": _monthly_editions(editions, now),
        "top": _top(in_period, limit),
        "newcomers": newcomers,
    }


def get_edition_activity(
    days: Optional[int] = DEFAULT_DAYS, limit: int = DEFAULT_LIMIT
) -> dict:
    """Cached version of compute_edition_activity"""
    key = f"edition_activity:{period_key(days)}:{limit}"
    data = cache.get(key)
    if data is None:
        data = compute_edition_activity(days, limit)
        cache.set(key, data, CACHE_TIMEOUT_SECONDS)
    return data
