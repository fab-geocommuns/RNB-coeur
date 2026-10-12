import logging
from enum import IntEnum

import requests
from django.conf import settings

BREVO_SMTP_URL = "https://api.brevo.com/v3/smtp/email"
REQUEST_TIMEOUT_S = 10

logger = logging.getLogger(__name__)


class BrevoTemplate(IntEnum):
    """Ids of the transactional templates defined in the Brevo account."""

    REPORT_ACTIVITY = 75


class BrevoError(Exception):
    pass


def send_transactional_email(
    *, template: BrevoTemplate, to: str, params: dict[str, str]
) -> None:
    """
    Sends a Brevo transactional template to a single recipient.
    Sender and subject are defined in the Brevo template; params fill its
    {{ params.X }} placeholders, escaped by Brevo.
    When EMAIL_SENDING_ENABLED is off, the email is logged instead of sent.
    Raises BrevoError when Brevo refuses the request.
    """
    if not settings.EMAIL_SENDING_ENABLED:
        logger.info(
            "Email sending disabled, Brevo email logged instead: template=%s to=%s params=%s",
            template.name,
            to,
            params,
        )
        return

    response = requests.post(
        BREVO_SMTP_URL,
        headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
        json={
            "templateId": template.value,
            "to": [{"email": to}],
            "replyTo": {"email": settings.RNB_REPLY_TO_ADDRESS},
            "params": params,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    if not response.ok:
        # Brevo error bodies hold a code and a message, never the api key.
        raise BrevoError(f"Brevo HTTP {response.status_code}: {response.text[:500]}")
