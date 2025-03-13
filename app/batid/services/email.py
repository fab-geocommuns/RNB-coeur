from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def build_reset_password_email(token: str) -> EmailMultiAlternatives:

    html_content = render_to_string()

    msg = EmailMultiAlternatives(
        subject="Réinitialisation de votre mot de passe RNB",
    )

    pass
