from __future__ import annotations

from batid.models import EmailNotificationOptOut, Report, ReportMessage
from batid.services.brevo import BrevoTemplate, send_transactional_email
from batid.services.email import (
    make_unsubscribe_token,
    report_map_url,
    report_unsubscribe_url,
)
from django.contrib.auth.models import User

_REPORT_ACTIVITY_SUBJECTS = {
    "fix": "Votre signalement RNB a été traité",
    "reject": "Votre signalement RNB a été refusé",
    "comment": "Nouveau message sur votre signalement RNB",
}

_REPORT_ACTIVITY_LABELS = {
    "fix": "résolu",
    "reject": "refusé",
    "comment": "commenté",
}


def notify_report_author(
    *, report_id: int, action: str, actor_user_id: int, message_id: int
) -> None:
    """
    Loads the report, resolves the recipient email (created_by_user.email or
    created_by_email) and emails the author about the new activity through Brevo.

    Silently skips when: there is no recipient email; the author is the actor
    of the activity; the recipient email is opted out (EmailNotificationOptOut).
    """
    report = Report.objects.select_related("created_by_user", "building").get(
        id=report_id
    )

    recipient_email = _resolve_recipient_email(report)
    if not recipient_email:
        return

    actor = User.objects.get(id=actor_user_id)
    if _author_is_actor(report=report, actor=actor):
        return

    if EmailNotificationOptOut.is_opted_out(recipient_email):
        return

    message = ReportMessage.objects.get(id=message_id)
    send_transactional_email(
        template=BrevoTemplate.REPORT_ACTIVITY,
        to=recipient_email,
        params={
            "SUBJECT": _REPORT_ACTIVITY_SUBJECTS[action],
            "ACTIVITY_LABEL": _REPORT_ACTIVITY_LABELS[action],
            "MESSAGE_TEXT": message.text,
            "REPORT_URL": report_map_url(report),
            "UNSUBSCRIBE_URL": report_unsubscribe_url(
                make_unsubscribe_token(recipient_email)
            ),
        },
    )


def _resolve_recipient_email(report: Report) -> str | None:
    if report.created_by_user_id is not None:
        return report.created_by_user.email or None
    return report.created_by_email or None


def _author_is_actor(*, report: Report, actor: User) -> bool:
    if report.created_by_user_id is not None:
        return report.created_by_user_id == actor.id
    # Anonymous report: the actor may be its author, now logged in.
    return bool(actor.email) and report.created_by_email.lower() == actor.email.lower()
