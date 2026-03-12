import datetime

from django.contrib.auth.models import User
from django.db.models import Count

from batid.models.building import BuildingWithHistory


def get_monthly_edit_leaderboard(year: int, month: int) -> list[dict]:
    """
    Input: year and month (e.g. 2026, 2 for February 2026).
    Returns: list of dicts sorted by edit_count desc, e.g.:
        [{"event_user__username": "alice", "event_user__email": "alice@example.com", "edit_count": 42}, ...]
    A single event_id touching N buildings counts as 1 edit.
    Excludes rows with no event_user.
    """
    start, end = _month_bounds(year, month)
    return list(
        BuildingWithHistory.objects.filter(event_user__isnull=False)
        .extra(
            where=["lower(sys_period) >= %s AND lower(sys_period) < %s"],
            params=[start, end],
        )
        .values("event_user__username", "event_user__email")
        .annotate(edit_count=Count("event_id", distinct=True))
        .order_by("-edit_count")
    )


def get_monthly_new_users(year: int, month: int):
    """
    Input: year and month.
    Returns: User queryset of non-staff users who joined in the given month and have an email.
    """
    start, end = _month_bounds(year, month)
    return User.objects.filter(
        date_joined__gte=start,
        date_joined__lt=end,
        is_staff=False,
    ).exclude(email="")


def _month_bounds(year: int, month: int) -> tuple:
    start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    if month == 12:
        end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
    else:
        end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.timezone.utc)
    return start, end
