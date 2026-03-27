from django.contrib.auth.models import User
from django.db import connection

from batid.utils.date import french_month_year_label
from batid.utils.date import month_bounds
from batid.utils.date import previous_month
from batid.utils.db import dictfetchall


def get_monthly_edit_leaderboard(year: int, month: int) -> list[dict]:
    """
    Input: year and month (e.g. 2026, 2 for February 2026).
    Returns: list of dicts sorted by edit_count desc, e.g.:
        [{"username": "alice", "edit_count": 42}, ...]
    A single event_id touching N buildings counts as 1 edit.
    Excludes rows with no event_user.
    """
    start, end = month_bounds(year, month)

    with connection.cursor() as cursor:

        q = """
            SELECT u.username, u.email, COUNT(DISTINCT bdg.event_id) as edit_count
            FROM batid_building_with_history bdg
            INNER JOIN auth_user u on u.id = bdg.event_user_id
            WHERE lower(bdg.sys_period) >= %(start)s AND lower(bdg.sys_period) < %(end)s
            AND bdg.event_origin ->> 'source' = 'contribution'
            GROUP BY u.username, u.email
            ORDER BY edit_count DESC;
        """

        params = {"start": start, "end": end}

        return dictfetchall(cursor, q, params)


def get_monthly_new_users(year: int, month: int):
    """
    Input: year and month.
    Returns: User queryset of non-staff users who joined in the given month and have an email.
    """
    start, end = month_bounds(year, month)
    return User.objects.filter(
        date_joined__gte=start,
        date_joined__lt=end,
        is_staff=False,
    ).exclude(email="")


def send_monthly_leaderboard_emails() -> str:
    """
    Computes the leaderboard for the previous month and sends an email to each eligible recipient
    (users who edited the RNB or created an account that month, with a non-empty email).
    Returns a summary message.
    """
    from batid.services.email import build_monthly_leaderboard_email

    year, month = previous_month()

    leaderboard = get_monthly_edit_leaderboard(year, month)
    if not leaderboard:
        return "No edits this month, no emails sent"

    label = french_month_year_label(year, month)
    new_users = get_monthly_new_users(year, month)

    editor_emails = {entry["email"] for entry in leaderboard if entry.get("email")}
    new_user_emails = set(new_users.values_list("email", flat=True))
    recipient_emails = editor_emails | new_user_emails

    msg = build_monthly_leaderboard_email(year, month)
    sent = 0
    for email in recipient_emails:
        msg.to = [email]
        msg.send()
        sent += 1

    return f"Sent {sent} emails for {label}"
