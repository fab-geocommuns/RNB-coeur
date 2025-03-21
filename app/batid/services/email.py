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
        headers={"Reply-To": settings.RNB_REPLY_TO_ADDRESS},
        to=[email],
    )

    msg.attach_alternative(html_content, "text/html")

    return msg


def _reset_password_url(user_id_b64: str, token: str) -> str:

    site_url = os.environ.get("FRONTEND_URL")
    return f"{site_url}/reset_password/{user_id_b64}/{token}"


def get_rnb_email_sender() -> str:
    return f"{settings.RNB_SEND_NAME} <{settings.RNB_SEND_ADDRESS}>"
