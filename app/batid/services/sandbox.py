import logging

import sentry_sdk
from django.conf import settings
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


def build_sandbox_user_payload(user: User) -> dict:
    """Build the payload sent to the sandbox API for a production user."""
    profile = getattr(user, "profile", None)
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "username": user.username,
        "job_title": getattr(profile, "job_title", None),
    }


def mirror_user_to_sandbox(user: User) -> None:
    """Queue the creation of the sandbox counterpart of a production user.

    Every code path that creates a production account must call this, so that a
    user can work on the sandbox with the same identity. Prefer calling it from
    transaction.on_commit() so the task never reaches the worker before the user
    row is committed.

    No-op on instances that have no sandbox (the sandbox itself, staging, local
    dev). Never raises: a broker outage must not break an ongoing signup or
    login, so failures are reported and swallowed.
    """
    if not settings.HAS_SANDBOX:
        return

    # Deferred import: batid.tasks imports batid.services at module level.
    from batid.tasks import create_sandbox_user

    try:
        create_sandbox_user.delay(build_sandbox_user_payload(user))
    except Exception:
        logger.exception(
            "Failed to queue the sandbox mirroring of user %s (non-fatal)", user.pk
        )
        sentry_sdk.capture_exception()
