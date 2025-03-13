import os

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def build_reset_password_email(token: str, email: str) -> EmailMultiAlternatives:

    # ###########
    # Build the email content

    # First the site url to change password
    url = _reset_password_url(token)

    html_content = render_to_string("emails/reset_password.html", {"url": url})

    msg = EmailMultiAlternatives(
        subject="Réinitialisation de votre mot de passe RNB",
        body="Veuillez consulter la version HTML de cet email.",
        from_email="dummy@dummy.com",
        to=[email],
    )

    msg.attach_alternative(html_content, "text/html")

    return msg


def _reset_password_url(token: str) -> str:

    site_url = os.environ.get("FRONTEND_URL")
    return f"{site_url}/reset_password/{token}"
