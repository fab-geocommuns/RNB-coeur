"""
Summary of the community contributions shown on the home page of the website
(GET /api/alpha/contributions/summary/ for one period,
GET /api/alpha/contributions/summaries/ for all of them).

Everything is computed during the request, for every period at once (the last
7 or 30 days, and every contribution ever made), then cached
for an hour.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from batid.models import City, Department, SummerChallenge
from batid.services.RNB_team_user import RNB_TEAM_USERNAME
from batid.utils.db import dictfetchall
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.db.models import (
    Case,
    Count,
    Min,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    When,
)
from django.db.models.functions import Left
from django.utils import timezone

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")

# The window is a rolling one, so that the figures do not drop to zero on the
# 1st of the month: the last 7 or 30 days
WINDOWS_DAYS = [7, 30]
DEFAULT_WINDOW_DAYS = 30
# The whole period, asked with days=all, has no start: every contribution is
# counted, as in the internal Metabase dashboard
ALL_PERIOD = "all"
TOP_LIMIT = 5
# cities in the long rankings of the details page (GET .../rankings/): every
# contributor and organization is listed, but up to 20 000 cities have
# contributions over the whole period
RANKED_CITIES_LIMIT = 100
# contributors listed as newcomers
NEWCOMERS_LIMIT = 8

CACHE_KEY = "contribution_summary"
# version of the response format, in the cache key: an entry cached by the
# previous code (v3: without the long rankings) is never read
CACHE_FORMAT_VERSION = "v4"
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

# A contribution is one Contribution row: every edition request (creation,
# update, merge, split…) writes exactly one, whatever the number of buildings
# it touches. The internal Metabase dashboard counts the editions the same way.
# Until 2025, some rows are older fixed reports kept by migration 0138: the
# contribution is then dated by the report and counted for the user who
# handled it (review_user, renamed user by 0139). They are mixed with editions
# (February 2025) and go on until September 2025, so no date splits the two.
# In SummerChallenge, the only rows with a city, a contribution is one distinct
# event_id: a single update (eg. shape + address) writes several rows sharing
# the same event_id.
#
# The whole computation, for every period, takes 3 queries: one pass over the
# contributions, one over the cities, and the ranked cities. The passes group the rows first and only then look up the names, for
# each group: joining the names before grouping is several times slower.


def _technical_user() -> QuerySet:
    """
    Id of the technical RNB account, as a subquery. Excluding it by username
    joins auth_user, and Postgres, which expects a single row in a recent
    window, then compares every row with every user (8 s over 7 days)
    """
    return User.objects.filter(username=RNB_TEAM_USERNAME).values("id")


def city_contributions() -> QuerySet:
    """
    SummerChallenge rows of the contributions, the only ones that know the
    city of the edited building. They only exist since 7 July 2025: the cities
    of the editions made before are not counted. Only contributions write rows
    (Building.update and deactivate() check the event origin), except the
    imports run by the technical RNB account, which is left out. Not every
    contribution writes one: a reactivation (Building.reactivate) writes none,
    nor does an update that changes nothing (Building.update only scores real
    changes), so they count as contributions but not for their city.
    """
    return SummerChallenge.objects.exclude(user_id__in=_technical_user())


def public_username(username: str) -> str:
    """Some usernames are email addresses: only their local part is shown"""
    return username.split("@")[0]


def organization_label(short_name: Optional[str], name: str) -> str:
    """
    Name under which an organization is shown, the same in every ranking: its
    short name if any, else its name
    """
    return short_name or name


def _period_start(now: datetime, days: Optional[int]) -> Optional[datetime]:
    """Start of the last `days` days, or None (no start) for the whole period"""
    return None if days is None else now - timedelta(days=days)


def _isoformat(since: Optional[datetime]) -> Optional[str]:
    """ISO date of a period start, None for the whole period (no start)"""
    return None if since is None else since.isoformat()


def _is_in(first_at: datetime, since: Optional[datetime]) -> bool:
    """Whether a date is in the period starting at `since` (None: no start)"""
    return since is None or first_at >= since


def _period_counts_annotations(
    starts: dict[str, Optional[datetime]], count: Callable[[Q], Count]
) -> dict[str, Count]:
    """{"n_<period key>": number of contributions since the start of the period}"""
    return {
        f"n_{key}": count(Q() if since is None else Q(created_at__gte=since))
        for key, since in starts.items()
    }


def _user_stats(now: datetime, starts: dict[str, Optional[datetime]]) -> list[dict]:
    """
    Query 1/3, one pass over the Contribution rows for every period at once.
    Per contributor (user_id None for a contribution without user): the date
    of their very first contribution ("first_at"), their number of
    contributions since each start ("n_<period key>"), their username, whether
    their account is active, and their current organization. The RNB team
    members count as any other contributor; the technical RNB account is left
    out: it runs the imports and data fixes, which write no Contribution row
    anyway.
    In SQL: grouped first, in parallel, then joined to the names of the ~500
    contributors. The ORM can only look the names up with subqueries in the
    SELECT, which forbid the parallel grouping (twice slower).
    """
    # the period keys are ours ("7", "30", "all"), never a user input
    counts = ",\n".join(
        (
            f'count(*) AS "n_{key}"'
            if since is None
            else f'count(*) FILTER (WHERE created_at >= %(since_{key})s) AS "n_{key}"'
        )
        for key, since in starts.items()
    )
    sql = f"""
        WITH stats AS (
            SELECT user_id, min(created_at) AS first_at,
                {counts}
            FROM batid_contribution
            WHERE created_at < %(now)s
              AND (
                  user_id IS NULL
                  OR user_id NOT IN (
                      SELECT id FROM auth_user WHERE username = %(technical)s
                  )
              )
            GROUP BY user_id
        )
        SELECT stats.*, u.username, u.is_active, p.organization_id,
            o.name AS organization_name, o.short_name AS organization_short_name
        FROM stats
        LEFT JOIN auth_user u ON u.id = stats.user_id
        LEFT JOIN batid_userprofile p ON p.user_id = stats.user_id
        LEFT JOIN batid_organization o ON o.id = p.organization_id
    """  # nosec B608: only the period keys ("7", "30", "all") are formatted in, the dates are query parameters
    params = {"now": now, "technical": RNB_TEAM_USERNAME} | {
        f"since_{key}": since for key, since in starts.items() if since is not None
    }
    with connection.cursor() as cursor:
        return dictfetchall(cursor, sql, params)


def _city_stats(now: datetime, starts: dict[str, Optional[datetime]]) -> list[dict]:
    """
    Query 2/3, one pass over the SummerChallenge rows for every period at
    once. Per city: the date of its first contribution since 7 July 2025, when
    the rows start ("first_at"), and its number of contributions since each
    start ("n_<period key>"), the distinct events counted from the covering
    index sc_city_event_idx alone. A city edited before that date and again
    after is counted, and new if that later edition is in the period.
    """
    return list(
        city_contributions()
        .filter(created_at__lt=now, city_id__isnull=False)
        .values("city_id")
        .annotate(
            first_at=Min("created_at"),
            **_period_counts_annotations(
                starts, lambda q: Count("event_id", distinct=True, filter=q)
            ),
        )
        .order_by()
    )


def _city_details(ids: set[int]) -> dict[int, dict]:
    """
    Query 3/3: INSEE code, name and department of cities, by id. Cities have
    no department of their own: its code is the start of the INSEE code (3
    characters overseas, as 977 Saint-Barthélemy, 2 elsewhere, as 2A Corse-du-
    Sud). It matches the department of every contributed city.
    """
    return {
        c["id"]: dict(c)
        for c in City.objects.filter(id__in=ids)
        .annotate(
            department_code=Case(
                When(code_insee__startswith="97", then=Left("code_insee", 3)),
                default=Left("code_insee", 2),
            )
        )
        .annotate(
            department_name=Subquery(
                Department.objects.filter(code=OuterRef("department_code")).values(
                    "name"
                )
            )
        )
        .values("id", "code_insee", "name", "department_code", "department_name")
    }


def _department(city: dict) -> Optional[dict]:
    """{"code", "name"} of the department of a city of _city_details, if any"""
    if city["department_name"] is None:
        return None
    return {"code": city["department_code"], "name": city["department_name"]}


def _organization_stats(users: list[dict], keys: list[str]) -> list[dict]:
    """
    The contributor stats summed by organization (the current one of each
    contributor): its very first contribution is the earliest of its members
    """
    organizations: dict[int, dict] = {}
    for user in users:
        if user["organization_id"] is None:
            continue
        stats = organizations.setdefault(
            user["organization_id"],
            {
                "id": user["organization_id"],
                "name": organization_label(
                    user["organization_short_name"], user["organization_name"]
                ),
                "first_at": user["first_at"],
            }
            | {f"n_{key}": 0 for key in keys},
        )
        stats["first_at"] = min(stats["first_at"], user["first_at"])
        for key in keys:
            stats[f"n_{key}"] += user[f"n_{key}"]
    return list(organizations.values())


def _period_counts(stats: list[dict], key: str, since: Optional[datetime]) -> dict:
    """
    Number of cities or organizations that contributed in the period, and of
    those whose very first contribution is in it
    """
    active = [s for s in stats if s[f"n_{key}"]]
    return {
        "total": len(active),
        "new": sum(1 for s in active if _is_in(s["first_at"], since)),
    }


def _ranked(
    stats: list[dict], key: str, id_field: str, limit: Optional[int] = None
) -> list[dict]:
    """
    The rows of `stats` with contributions in the period, the most active
    first, the `limit` first ones only if given. Ties are broken by id, so
    that the order is stable.
    """
    active = [s for s in stats if s[f"n_{key}"] and s[id_field] is not None]
    return sorted(active, key=lambda s: (-s[f"n_{key}"], s[id_field]))[:limit]


def _listed(users: list[dict]) -> list[dict]:
    """
    The contributors that may be published by name: a deactivated account
    (spam, departure, request of the person) is left out from the next
    computation (the cached one keeps it until then, up to an hour, a day if
    the refresh fails), but its contributions still count for the totals and
    for its organization. A contribution without user (is_active NULL) is
    never listed either.
    """
    return [u for u in users if u["is_active"]]


def _ranked_lists(
    users: list[dict],
    organizations: list[dict],
    cities: list[dict],
    city_details: dict[int, dict],
    key: str,
) -> dict:
    """
    Every contributor and organization of the period, and its
    RANKED_CITIES_LIMIT most edited cities, the most active first. The top of
    the summary is the start of these lists.
    """
    return {
        "users": [
            {
                "username": public_username(u["username"]),
                "organization": (
                    organization_label(
                        u["organization_short_name"], u["organization_name"]
                    )
                    if u["organization_name"]
                    else None
                ),
                "count": u[f"n_{key}"],
            }
            for u in _ranked(_listed(users), key, "user_id")
        ],
        # by the contributions of their current members. No department: a
        # national organization contributes everywhere
        "organizations": [
            {"name": o["name"], "count": o[f"n_{key}"]}
            for o in _ranked(organizations, key, "id")
        ],
        "cities": [
            {
                "insee_code": city_details[c["city_id"]]["code_insee"],
                "name": city_details[c["city_id"]]["name"],
                "department": _department(city_details[c["city_id"]]),
                "count": c[f"n_{key}"],
            }
            for c in _ranked(cities, key, "city_id", RANKED_CITIES_LIMIT)
        ],
    }


def _newcomers(users: list[dict], key: str, since: Optional[datetime]) -> list[dict]:
    """
    Listed contributors whose very first contribution is in the period, the
    latest first
    """
    return sorted(
        (u for u in _listed(users) if u[f"n_{key}"] and _is_in(u["first_at"], since)),
        key=lambda u: (u["first_at"], u["user_id"]),
        reverse=True,
    )[:NEWCOMERS_LIMIT]


def _summaries(now: datetime, periods: dict[str, Optional[int]]) -> dict[str, dict]:
    """
    Summary of each period ({key: days}, days None for the whole period), in
    3 queries for all of them, all at the same instant: a shorter period is
    always included in a longer one
    """
    now = now.astimezone(PARIS_TZ)
    starts = {key: _period_start(now, days) for key, days in periods.items()}
    users = _user_stats(now, starts)
    cities = _city_stats(now, starts)
    organizations = _organization_stats(users, list(periods))
    city_details = _city_details(
        {
            c["city_id"]
            for key in periods
            for c in _ranked(cities, key, "city_id", RANKED_CITIES_LIMIT)
        }
    )
    rankings = {
        key: _ranked_lists(users, organizations, cities, city_details, key)
        for key in periods
    }

    return {
        key: {
            "updated_at": now.isoformat(),
            # null for the whole period, which has no start
            "window_days": days,
            "since": _isoformat(starts[key]),
            # cities and organizations that contributed in the period, and those
            # whose very first contribution is in it
            "cities": _period_counts(cities, key, starts[key]),
            "organizations": _period_counts(organizations, key, starts[key]),
            # edition requests of the period, one per request: the imports
            # (BD TOPO, BAL) write no Contribution row and are left out
            "contributions": {"total": sum(u[f"n_{key}"] for u in users)},
            "top": {name: ranked[:TOP_LIMIT] for name, ranked in rankings[key].items()},
            # long version of "top", left out of the summary (see
            # _without_rankings), served by get_all_contribution_rankings
            "rankings": rankings[key],
            "newcomers": {
                "users": [
                    {"username": public_username(u["username"])}
                    for u in _newcomers(users, key, starts[key])
                ],
            },
        }
        for key, days in periods.items()
    }


def compute_contribution_summary(
    now: Optional[datetime] = None,
    days: Optional[int] = DEFAULT_WINDOW_DAYS,
) -> dict:
    """
    Summary of the last `days` days, or of every contribution if None. See
    the GET /api/alpha/contributions/summary/ documentation for the format.
    """
    key = str(days or ALL_PERIOD)
    return _without_rankings(_summaries(now or timezone.now(), {key: days})[key])


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
    "all"), all computed from the same pass over the contributions: a shorter
    period never counts more cities or organizations than a longer one. Still
    not covered: a row updated meanwhile (a user changing organization), until the next refresh.
    """
    return _summaries(
        now or timezone.now(),
        {key: None if key == ALL_PERIOD else int(key) for key in PERIOD_KEYS},
    )


def summaries_cache_key() -> str:
    """
    Key of the single entry holding every period. It names the periods: an
    entry cached before a period was added (by the previous code during a
    deploy, or until it expires) is never read.
    """
    return f"{CACHE_KEY}:{CACHE_FORMAT_VERSION}:{','.join(PERIOD_KEYS)}"


def _without_rankings(summary: dict) -> dict:
    """A cached summary without its long rankings, served apart"""
    return {k: v for k, v in summary.items() if k != "rankings"}


def get_contribution_summary(days: Optional[int] = DEFAULT_WINDOW_DAYS) -> dict:
    """
    Cached version of compute_contribution_summary. All the periods share a
    single entry and are recomputed together, so that they stay consistent.
    """
    return _without_rankings(
        _cached(summaries_cache_key(), compute_all_summaries)[str(days or ALL_PERIOD)]
    )


def get_all_contribution_summaries() -> list[dict]:
    """
    Summaries of every period, shortest first, read from the cache at once:
    they always come from the same computation. Separate calls to
    get_contribution_summary may not (one may get the outdated entry served
    during a refresh, the next the new one).
    """
    summaries = _cached(summaries_cache_key(), compute_all_summaries)
    return [_without_rankings(summaries[key]) for key in PERIOD_KEYS]


def get_all_contribution_rankings() -> list[dict]:
    """
    Long rankings of every period, shortest first: every contributor and
    organization, and the RANKED_CITIES_LIMIT most edited cities. They come
    from the same cached computation as the summaries.
    """
    summaries = _cached(summaries_cache_key(), compute_all_summaries)
    return [
        {
            "updated_at": summaries[key]["updated_at"],
            "window_days": summaries[key]["window_days"],
            "since": summaries[key]["since"],
        }
        | summaries[key]["rankings"]
        for key in PERIOD_KEYS
    ]
