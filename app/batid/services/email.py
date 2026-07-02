import os

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

UNSUBSCRIBE_SALT = "report-notification-unsubscribe"


def build_reset_password_email(
    token: str, user_id_b64: str, email: str
) -> EmailMultiAlternatives:

    # ###########
    # Build the email content

    # First the site url to change password
    url = _reset_password_url(user_id_b64, token)

    html_content = render_to_string("emails/reset_password.html", {"url": url})

    msg = EmailMultiAlternatives(
        subject="Réinitialisation de votre mot de passe RNB",
        body="Veuillez consulter la version HTML de cet email.",
        from_email=get_rnb_email_sender(),
        headers={"Reply-To": settings.RNB_REPLY_TO_ADDRESS},  # type: ignore
        to=[email],
    )

    msg.attach_alternative(html_content, "text/html")

    return msg


def _reset_password_url(user_id_b64: str, token: str) -> str:
    site_url = settings.FRONTEND_URL
    return f"{site_url}/auth/mdp-nouveau/{user_id_b64}/{token}"


def get_rnb_email_sender() -> str:
    return f"{settings.RNB_SEND_NAME} <{settings.RNB_SEND_ADDRESS}>"


def activate_account_url(user_id_b64: str, token: str) -> str:
    backend_site_url = os.environ.get("URL")
    return f"{backend_site_url}/api/alpha/auth/activate/{user_id_b64}/{token}/"


def build_monthly_leaderboard_email(
    year: int,
    month: int,
) -> EmailMultiAlternatives:
    """
    Input:
        year: e.g. 2026
        month: e.g. 2 for February
    Returns: EmailMultiAlternatives with to=[] (no recipient set).
    Set msg.to = [email] before each msg.send() in the caller loop.
    """
    from batid.services.leaderboard import (
        get_monthly_edit_leaderboard,
        get_monthly_new_users,
    )
    from batid.utils.date import french_month_year_label

    leaderboard = get_monthly_edit_leaderboard(year, month)
    month_year_label = french_month_year_label(year, month)
    new_users = get_monthly_new_users(year, month)
    new_usernames = list(new_users.values_list("username", flat=True))

    total_contributions = sum(entry["edit_count"] for entry in leaderboard)

    html_content = render_to_string(
        "emails/monthly_leaderboard.html",
        {
            "leaderboard": leaderboard,
            "month_year_label": month_year_label,
            "new_usernames": sorted(new_usernames, key=str.lower),
            "total_contributions": total_contributions,
        },
    )
    msg = EmailMultiAlternatives(
        subject=f"Contributions RNB – {month_year_label}",
        body="Veuillez consulter la version HTML de cet email.",
        from_email=get_rnb_email_sender(),
        headers={"Reply-To": settings.RNB_REPLY_TO_ADDRESS},  # type: ignore
        to=[],
    )
    msg.attach_alternative(html_content, "text/html")
    return msg


def build_activate_account_email(
    token: str, user_id_b64: str, email: str
) -> EmailMultiAlternatives:
    url = activate_account_url(user_id_b64, token)
    html_content = render_to_string("emails/activate_account.html", {"url": url})
    msg = EmailMultiAlternatives(
        subject="Activez votre compte RNB",
        body="Veuillez consulter la version HTML de cet email.",
        from_email=get_rnb_email_sender(),
        headers={"Reply-To": settings.RNB_REPLY_TO_ADDRESS},  # type: ignore
        to=[email],
    )
    msg.attach_alternative(html_content, "text/html")
    return msg


def make_unsubscribe_token(email: str) -> str:
    """Signs the (lowercased) email into a stateless, non-expiring token."""
    return signing.dumps(email.lower(), salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token: str) -> str:
    """
    Returns the email embedded in the token.
    Raises signing.BadSignature if the token has been tampered with.
    """
    return signing.loads(token, salt=UNSUBSCRIBE_SALT)


def report_map_url(report) -> str:
    """
    Builds the link to the RNB map focused on the report.
    Format: {FRONTEND_URL}/carte?report={id}&extra_layers=reports&q={rnb_id}
    The q parameter (rnb_id) is omitted when the report has no building.
    """
    url = f"{settings.FRONTEND_URL}/carte?report={report.id}&extra_layers=reports"
    if report.building is not None:
        url += f"&q={report.building.rnb_id}"
    return url


def report_unsubscribe_url(token: str) -> str:
    return f"{settings.FRONTEND_URL}/notifications/desinscription?token={token}"


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


def build_report_activity_email(
    report, action: str, message, recipient_email: str
) -> EmailMultiAlternatives:
    """
    Input: report, action ("fix"/"reject"/"comment"), message (ReportMessage added),
           recipient_email (the recipient).
    Returns: EmailMultiAlternatives ready to send, containing the message text,
             the map link and the signed unsubscribe link (token on recipient_email).
    """
    unsubscribe_token = make_unsubscribe_token(recipient_email)
    html_content = render_to_string(
        "emails/report_activity.html",
        {
            "activity_label": _REPORT_ACTIVITY_LABELS[action],
            "message_text": message.text,
            "report_url": report_map_url(report),
            "unsubscribe_url": report_unsubscribe_url(unsubscribe_token),
        },
    )
    msg = EmailMultiAlternatives(
        subject=_REPORT_ACTIVITY_SUBJECTS[action],
        body="Veuillez consulter la version HTML de cet email.",
        from_email=get_rnb_email_sender(),
        headers={"Reply-To": settings.RNB_REPLY_TO_ADDRESS},  # type: ignore
        to=[recipient_email],
    )
    msg.attach_alternative(html_content, "text/html")
    return msg
