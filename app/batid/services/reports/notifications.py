from __future__ import annotations

from batid.models import EmailNotificationOptOut, Report, ReportMessage
from batid.services.brevo import BrevoTemplate, send_transactional_email
from batid.services.email import (
    make_unsubscribe_token,
    report_map_url,
    report_unsubscribe_url,
)

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
    Emails the author of the report about the new activity through Brevo.

    Only reports created by an account are notified: the email of an anonymous
    report is never verified, so anyone could otherwise make RNB send their
    reply text to any address.

    Silently skips when: the report is anonymous; the author account has no
    email; the author is the actor of the activity; the author email is opted
    out (EmailNotificationOptOut).
    """
    report = Report.objects.select_related("created_by_user", "building").get(
        id=report_id
    )

    author = report.created_by_user
    if author is None or not author.email:
        return

    if author.id == actor_user_id:
        return

    recipient_email = author.email
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
