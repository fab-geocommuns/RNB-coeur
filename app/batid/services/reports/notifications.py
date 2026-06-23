from __future__ import annotations

import logging

from batid.models import EmailNotificationOptOut, Report, ReportMessage
from batid.services.email import build_report_activity_email

logger = logging.getLogger(__name__)


def notify_report_author(
    report_id: int,
    action: str,
    actor_user_id: int | None,
    actor_email: str | None,
    message_id: int,
) -> None:
    """
    Loads the report, resolves the recipient email (created_by_user.email or
    created_by_email) and emails the author about the new activity.

    Silently skips when: there is no recipient email; the author is the actor
    of the activity; the recipient email is opted out (EmailNotificationOptOut).
    """
    report = Report.objects.select_related("created_by_user", "building").get(
        id=report_id
    )

    recipient_email = _resolve_recipient_email(report)
    if not recipient_email:
        return

    if _author_is_actor(report, actor_user_id, actor_email):
        return

    if EmailNotificationOptOut.is_opted_out(recipient_email):
        return

    message = ReportMessage.objects.get(id=message_id)
    email = build_report_activity_email(report, action, message, recipient_email)
    email.send()


def _resolve_recipient_email(report: Report) -> str | None:
    if report.created_by_user_id is not None:
        return report.created_by_user.email or None
    return report.created_by_email or None


def _author_is_actor(
    report: Report, actor_user_id: int | None, actor_email: str | None
) -> bool:
    if (
        report.created_by_user_id is not None
        and actor_user_id is not None
        and report.created_by_user_id == actor_user_id
    ):
        return True
    if (
        report.created_by_email
        and actor_email
        and report.created_by_email.lower() == actor_email.lower()
    ):
        return True
    return False
