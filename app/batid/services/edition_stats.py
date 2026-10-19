from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from batid.models import BuildingWithHistory, Department, SummerChallenge
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Count, Exists, F, Min, OuterRef, QuerySet
from django.db.models.fields.json import KT
from django.db.models.functions import TruncMonth
from django.utils import timezone

# Months are calendar months in the French metropolitan timezone
PARIS_TZ = ZoneInfo("Europe/Paris")

PERIOD_CURRENT_MONTH = "current_month"
PERIOD_LAST_MONTH = "last_month"
PERIOD_ALL = "all"
PERIODS = [PERIOD_CURRENT_MONTH, PERIOD_LAST_MONTH, PERIOD_ALL]

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


def period_bounds(
    period: str, now: Optional[datetime] = None
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Returns the (since, until) datetimes of a period, until being exclusive.
    None means unbounded.
    """
    now = (now or timezone.now()).astimezone(PARIS_TZ)
    month_start = datetime(now.year, now.month, 1, tzinfo=PARIS_TZ)

    if period == PERIOD_CURRENT_MONTH:
        return month_start, None
    if period == PERIOD_LAST_MONTH:
        if now.month == 1:
            last_month_start = datetime(now.year - 1, 12, 1, tzinfo=PARIS_TZ)
        else:
            last_month_start = datetime(now.year, now.month - 1, 1, tzinfo=PARIS_TZ)
        return last_month_start, month_start
    if period == PERIOD_ALL:
        return None, None
    raise ValueError(f"Unknown period: {period}")


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


def _top(editions: QuerySet, since, until, limit: int) -> dict[str, list[dict]]:
    qs = _filter_dates(editions, "created_at", since, until)

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


def _newcomers(editions: QuerySet, since, until, limit: int) -> dict[str, list[dict]]:
    """
    Users, cities and departments whose very first contribution is in the period,
    the most recent first.
    """

    counts = {}

    def first_editions(key: str, rows: QuerySet) -> list[dict]:
        rows = rows.annotate(first_edition_at=Min("created_at"))
        rows = _filter_dates(rows, "first_edition_at", since, until)
        counts[key] = rows.count()
        return list(rows.order_by("-first_edition_at")[:limit])

    users = first_editions(
        "users", editions.values("user_id", username=F("user__username"))
    )
    org_names = _organization_short_names([u["user_id"] for u in users])

    cities = first_editions("cities", _city_rows(editions))
    departments_by_id = _departments(cities)

    departments = first_editions(
        "departments",
        editions.exclude(department__isnull=True).values(
            "department_id", code=F("department__code"), name=F("department__name")
        ),
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


def _previous_period(editions: QuerySet, period: str, now: datetime) -> Optional[dict]:
    """
    Number of editions of the period used to show a trend:
    - current_month: last month, from its first day up to the same elapsed time
      (so that a partial month is compared with a partial month)
    - last_month: the whole month before
    - all: no comparison
    """
    since, until = period_bounds(period, now)
    if period == PERIOD_CURRENT_MONTH:
        previous_since = _add_months(since, -1)
        previous_until = previous_since + (now - since)
    elif period == PERIOD_LAST_MONTH:
        previous_since = _add_months(since, -1)
        previous_until = since
    else:
        return None

    count = _filter_dates(
        editions, "created_at", previous_since, previous_until
    ).aggregate(editions=CONTRIBUTIONS)["editions"]
    return {
        "since": previous_since.date().isoformat(),
        "until": (previous_until.astimezone(PARIS_TZ)).isoformat(),
        "editions": count,
    }


def _date_or_none(dt: Optional[datetime]) -> Optional[str]:
    return dt.date().isoformat() if dt else None


def compute_edition_activity(
    period: str, limit: int = DEFAULT_LIMIT, now: Optional[datetime] = None
) -> dict:
    """
    Contribution statistics of a period, computed from the SummerChallenge table:
    totals, rankings (users, organizations, cities, departments) and newcomers.
    See the GET /api/alpha/editions/activity/ documentation for the output format.
    """
    now = (now or timezone.now()).astimezone(PARIS_TZ)
    since, until = period_bounds(period, now)
    editions = contributions()
    in_period = _filter_dates(editions, "created_at", since, until)

    totals = in_period.aggregate(
        editions=CONTRIBUTIONS,
        cities=Count("city", distinct=True),
        editors=Count("user", distinct=True),
    )

    if period == PERIOD_ALL:
        newcomers: dict = {
            "users": [],
            "cities": [],
            "departments": [],
            "count": None,
        }
    else:
        newcomers = _newcomers(editions, since, until, limit)

    # until is exclusive: the last day of the period is the day before
    last_day: Optional[date] = None
    if until:
        last_day = (until.astimezone(PARIS_TZ) - timedelta(days=1)).date()

    return {
        "period": {
            "key": period,
            "since": _date_or_none(since),
            "until": last_day.isoformat() if last_day else None,
        },
        "available_periods": PERIODS,
        "updated_at": timezone.now().astimezone(PARIS_TZ).isoformat(),
        "totals": totals,
        "previous_period": _previous_period(editions, period, now),
        "monthly": _monthly_editions(editions, now),
        "top": _top(editions, since, until, limit),
        "newcomers": newcomers,
    }


def get_edition_activity(period: str, limit: int = DEFAULT_LIMIT) -> dict:
    """Cached version of compute_edition_activity"""
    key = f"edition_activity:{period}:{limit}"
    data = cache.get(key)
    if data is None:
        data = compute_edition_activity(period, limit)
        cache.set(key, data, CACHE_TIMEOUT_SECONDS)
    return data
