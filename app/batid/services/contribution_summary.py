"""
Summary of the community contributions shown on the home page of the website
(GET /api/alpha/contributions/summary/ for one period,
GET /api/alpha/contributions/summaries/ for all of them).

Everything is computed during the request, for every period at once (the last
7 or 30 days, and since the opening of the collaborative edition), then cached
for an hour.
"""

import logging
import time
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from batid.models import KPI, City, Department, Organization, SummerChallenge
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
    Max,
    Min,
    QuerySet,
    Sum,
)
from django.utils import timezone

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")

# The window is a rolling one, so that the figures do not drop to zero on the
# 1st of the month: the last 7 or 30 days
WINDOWS_DAYS = [7, 30]
DEFAULT_WINDOW_DAYS = 30
# The whole period, asked with days=all, starts at the opening of the
# collaborative edition: the contributions of the 2024 summer game are left out
ALL_PERIOD = "all"
EDITION_OPENING = datetime(2025, 4, 1, tzinfo=PARIS_TZ)
TOP_LIMIT = 5
# contributors listed as newcomers
NEWCOMERS_LIMIT = 8

CACHE_KEY = "contribution_summary"
# Raised when the format of a summary changes, so that an entry cached in the
# previous format (by the previous code during a deploy, or until it expires)
# is never read. 2: full and short names of the organizations
CACHE_FORMAT_VERSION = 2
# days parameter of every period, all cached in a single entry
PERIOD_KEYS = [*(str(d) for d in WINDOWS_DAYS), ALL_PERIOD]
# An entry is recomputed after an hour, but kept a day: while one request
# recomputes it, the others get the previous one instead of all running the
# same queries at once
CACHE_FRESH_SECONDS = 3600
CACHE_TIMEOUT_SECONDS = 24 * 3600
# longest expected computation; past it, another request may try again
REFRESH_LOCK_SECONDS = 60
# With an empty cache, how long the requests wait for the one computing it
# (below the 60 s nginx proxy timeout), and how often they check
EMPTY_CACHE_WAIT_SECONDS = 20
EMPTY_CACHE_POLL_SECONDS = 0.5

# A contribution is one distinct event_id: a single update (eg. shape + address)
# writes several SummerChallenge rows sharing the same event_id
CONTRIBUTIONS = Count("event_id", distinct=True)


def contributions() -> QuerySet:
    """
    SummerChallenge rows of the contributions, the RNB team members counted as
    any other contributor. Only contributions write rows (Building.update and
    deactivate() check the event origin), except the imports run by the
    technical RNB account, which is left out.
    """
    return SummerChallenge.objects.exclude(user__username=RNB_TEAM_USERNAME)


def public_username(username: str) -> str:
    """Some usernames are email addresses: only their local part is shown"""
    return username.split("@")[0]


def short_name_or_none(short_name: Optional[str]) -> Optional[str]:
    """Short name of an organization, None when it has none (null or "")"""
    return short_name or None


def _departments(ids: set[Optional[int]]) -> dict[int, dict]:
    """{"code", "name"} of departments, by id"""
    return {
        d["id"]: {"code": d["code"], "name": d["name"]}
        for d in Department.objects.filter(id__in=[i for i in ids if i]).values(
            "id", "code", "name"
        )
    }


def _distinct_count(in_window: QuerySet, field: str) -> int:
    """Number of distinct values of `field` (city_id…) in the window"""
    return (
        in_window.exclude(**{f"{field}__isnull": True}).values(field).distinct().count()
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


def _building_changes(now: datetime, days: Optional[int]) -> dict:
    """
    Building changes of the last `days` complete days (since the opening of the
    collaborative edition if None), from the daily KPIs: a building changed
    twice counts twice. A KPI covers a UTC day and is computed at 3 am UTC for
    the day before, so the window ends on the latest computed day: a day not
    computed yet would otherwise be missing from the sum. The contributions
    include the RNB team ones, the KPIs do not split them.
    """
    kpis = KPI.objects.filter(
        name__in=[
            KPI_BUILDING_CHANGES_IMPORT_BDTOPO,
            KPI_BUILDING_CHANGES_IMPORT_BAL,
            KPI_BUILDING_CHANGES_CONTRIBUTIONS,
        ],
    )
    last_day = kpis.filter(
        value_date__lt=now.astimezone(dt_timezone.utc).date()
    ).aggregate(last=Max("value_date"))["last"]
    if last_day is None:
        return {"total": 0, "contributions": 0}
    first_day = (
        EDITION_OPENING.date() if days is None else last_day - timedelta(days=days - 1)
    )
    sums = {
        row["name"]: row["value"]
        for row in kpis.filter(value_date__gte=first_day, value_date__lte=last_day)
        .values("name")
        .annotate(value=Sum("value"))
    }
    return {
        "total": int(sum(sums.values())),
        "contributions": int(sums.get(KPI_BUILDING_CHANGES_CONTRIBUTIONS, 0)),
    }


def _ranked(in_window: QuerySet, field: str) -> list[dict]:
    """
    The TOP_LIMIT values of `field` (user_id, city_id…) with the most
    contributions in the window, as {"id", "count"}. Grouped by the id alone:
    joining the names before grouping is several times slower over the whole
    period. Ties are broken by id, so that the order is stable.
    """
    return [
        {"id": row[field], "count": row["count"]}
        for row in in_window.exclude(**{f"{field}__isnull": True})
        .values(field)
        .annotate(count=CONTRIBUTIONS)
        .order_by("-count", field)[:TOP_LIMIT]
    ]


def _top_users(in_window: QuerySet) -> list[dict]:
    users = _ranked(in_window, "user_id")
    details = {
        u["id"]: u
        for u in User.objects.filter(id__in=[u["id"] for u in users]).values(
            "id",
            "username",
            "profile__organization__short_name",
            "profile__organization__name",
        )
    }
    return [
        {
            "username": public_username(details[u["id"]]["username"]),
            "organization": details[u["id"]]["profile__organization__name"],
            "organization_short_name": short_name_or_none(
                details[u["id"]]["profile__organization__short_name"]
            ),
            "count": u["count"],
        }
        for u in users
    ]


def _top_organizations(in_window: QuerySet) -> list[dict]:
    """
    Organizations ranked by the contributions of their current members. No
    department: a national organization contributes everywhere.
    """
    organizations = _ranked(in_window, "user__profile__organization_id")
    details = {
        o["id"]: o
        for o in Organization.objects.filter(
            id__in=[o["id"] for o in organizations]
        ).values("id", "name", "short_name")
    }
    return [
        {
            "name": details[o["id"]]["name"],
            "short_name": short_name_or_none(details[o["id"]]["short_name"]),
            "count": o["count"],
        }
        for o in organizations
    ]


def _top_cities(in_window: QuerySet) -> list[dict]:
    """
    The department of a city is taken from its rows, as cities have no
    department of their own
    """
    cities = _ranked(in_window, "city_id")
    ids = [c["id"] for c in cities]
    details = {
        c["id"]: c
        for c in City.objects.filter(id__in=ids).values("id", "code_insee", "name")
    }
    department_refs = {
        row["city_id"]: row["department_ref"]
        for row in in_window.filter(city_id__in=ids)
        .values("city_id")
        .annotate(department_ref=Min("department"))
    }
    departments = _departments(set(department_refs.values()))
    return [
        {
            "insee_code": details[c["id"]]["code_insee"],
            "name": details[c["id"]]["name"],
            # 0 is no department id: the city has no department
            "department": departments.get(department_refs.get(c["id"]) or 0),
            "count": c["count"],
        }
        for c in cities
    ]


def compute_contribution_summary(
    now: Optional[datetime] = None,
    days: Optional[int] = DEFAULT_WINDOW_DAYS,
) -> dict:
    """
    Summary of the last `days` days, or since the opening of the collaborative
    edition if None. See the GET /api/alpha/contributions/summary/
    documentation for the format.
    """
    now = (now or timezone.now()).astimezone(PARIS_TZ)
    since = EDITION_OPENING if days is None else now - timedelta(days=days)
    in_window = contributions().filter(created_at__gte=since, created_at__lt=now)

    new_user_ids = _first_time_ids(in_window, "user_id", since)
    # the latest first contributions first
    new_users = list(
        in_window.filter(user_id__in=new_user_ids)
        .values("user_id", username=F("user__username"))
        .annotate(first_contribution_at=Min("created_at"))
        .order_by("-first_contribution_at")[:NEWCOMERS_LIMIT]
    )

    return {
        "updated_at": now.isoformat(),
        # null for the whole period
        "window_days": days,
        "since": since.isoformat(),
        # cities and organizations that contributed in the period, and those
        # whose very first contribution is in it
        "cities": {
            "total": _distinct_count(in_window, "city_id"),
            "new": len(_first_time_ids(in_window, "city_id", since)),
        },
        "organizations": {
            "total": _distinct_count(in_window, "user__profile__organization_id"),
            "new": len(
                _first_time_ids(in_window, "user__profile__organization_id", since)
            ),
        },
        "building_changes": _building_changes(now, days),
        "top": {
            "users": _top_users(in_window),
            "organizations": _top_organizations(in_window),
            "cities": _top_cities(in_window),
        },
        # contributors whose very first contribution is in the period, the
        # latest first
        "newcomers": {
            "users": [{"username": public_username(u["username"])} for u in new_users],
        },
    }


def _cached(key: str, compute: Callable[[], dict]) -> dict:
    """
    Value of `compute` cached under `key`, computed by a single request at a
    time (it holds a lock):
    - an outdated entry is served to the other requests meanwhile;
    - with no entry at all (after a deploy, or a cache flush), the others
      wait for it, then compute it themselves if it still is not there;
    - if the computation fails, the outdated entry is served, if any.
    """
    entry = cache.get(key)
    if entry is not None and entry["fresh_until"] > time.time():
        return entry["data"]
    lock_key = f"{key}:refreshing"
    locked = cache.add(lock_key, True, REFRESH_LOCK_SECONDS)
    if not locked and entry is not None:
        return entry["data"]
    # past the wait, the request computes without the lock: slower for the
    # database if the computing request is stuck, but never an error
    deadline = time.monotonic() + EMPTY_CACHE_WAIT_SECONDS
    while not locked and time.monotonic() < deadline:
        time.sleep(EMPTY_CACHE_POLL_SECONDS)
        entry = cache.get(key)
        if entry is not None:
            return entry["data"]
        # the request computing it may have failed: take over
        locked = cache.add(lock_key, True, REFRESH_LOCK_SECONDS)
    if locked:
        # another request may have stored it and released the lock between
        # our read and our lock: read it again before computing
        latest = cache.get(key)
        if latest is not None and latest["fresh_until"] > time.time():
            cache.delete(lock_key)
            return latest["data"]
        entry = latest if latest is not None else entry
    try:
        data = compute()
        cache.set(
            key,
            {"data": data, "fresh_until": time.time() + CACHE_FRESH_SECONDS},
            CACHE_TIMEOUT_SECONDS,
        )
        return data
    except Exception:
        if entry is None:
            raise
        logger.exception("Contribution summary refresh failed, outdated one served")
        return entry["data"]
    finally:
        if locked:
            cache.delete(lock_key)


def compute_all_summaries(now: Optional[datetime] = None) -> dict[str, dict]:
    """
    Summaries of every period, keyed by their days parameter ("7", "30",
    "all"), all computed at the same instant: computed at different times, a
    shorter period could count more cities or organizations than a longer one.
    Shortest period first: a contribution committed during the computation is
    then only counted by longer periods. Still not covered: a daily KPI written
    meanwhile (building_changes) or a row updated meanwhile (a user changing
    organization), until the next refresh.
    """
    now = now or timezone.now()
    return {
        key: compute_contribution_summary(
            now=now, days=None if key == ALL_PERIOD else int(key)
        )
        for key in PERIOD_KEYS
    }


def summaries_cache_key() -> str:
    """
    Key of the single entry holding every period. It names the format version
    and the periods: an entry cached in a previous format or before a period
    was added (by the previous code during a deploy, or until it expires) is
    never read.
    """
    return f"{CACHE_KEY}:v{CACHE_FORMAT_VERSION}:{','.join(PERIOD_KEYS)}"


def get_contribution_summary(days: Optional[int] = DEFAULT_WINDOW_DAYS) -> dict:
    """
    Cached version of compute_contribution_summary. All the periods share a
    single entry and are recomputed together, so that they stay consistent.
    """
    return _cached(summaries_cache_key(), compute_all_summaries)[
        str(days or ALL_PERIOD)
    ]


def get_all_contribution_summaries() -> list[dict]:
    """
    Summaries of every period, shortest first, read from the cache at once:
    they always come from the same computation. Separate calls to
    get_contribution_summary may not (one may get the outdated entry served
    during a refresh, the next the new one).
    """
    summaries = _cached(summaries_cache_key(), compute_all_summaries)
    return [summaries[key] for key in PERIOD_KEYS]
