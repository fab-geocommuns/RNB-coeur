import os

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


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
    from batid.services.leaderboard import get_monthly_edit_leaderboard
    from batid.services.leaderboard import get_monthly_new_users
    from batid.utils.date import french_month_year_label

    leaderboard = get_monthly_edit_leaderboard(year, month)
    month_year_label = french_month_year_label(year, month)
    new_users = get_monthly_new_users(year, month)
    new_usernames = list(new_users.values_list("username", flat=True))

    html_content = render_to_string(
        "emails/monthly_leaderboard.html",
        {
            "leaderboard": leaderboard,
            "month_year_label": month_year_label,
            "new_usernames": new_usernames,
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
