import re
from enum import StrEnum

import django_otp
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from app.mfa_enforcement import MFAEnforcement

APP_DEVICE_NAME = "Application d'authentification"
BACKUP_DEVICE_NAME = "Codes de secours"
BACKUP_CODES_COUNT = 10

TOTP_CODE_PATTERN = re.compile(r"[0-9]{6}")


class MFAError(StrEnum):
    REQUIRED = "mfa_required"
    INVALID = "mfa_invalid"
    SETUP_REQUIRED = "mfa_setup_required"
    ALREADY_CONFIGURED = "mfa_already_configured"
    SETUP_NOT_STARTED = "mfa_setup_not_started"


class LoginMFAOutcome(StrEnum):
    """Login accepted; refusals are MFAError values."""

    GRANTED = "granted"
    SETUP_SUGGESTED = "setup_suggested"


def has_confirmed_app(user: User) -> bool:
    """Backup codes alone do not count: only a confirmed authenticator app does."""
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def verify_otp(*, user: User, otp) -> bool:
    """Check a code against the user's confirmed devices, oldest first, until one
    accepts it: a 6-digit code goes to the authenticator apps, then to the backup
    codes (staff can add numeric ones with `addstatictoken`); any other code goes
    to the backup codes only.

    Each device keeps its own throttling, so wrong backup codes never delay TOTP
    codes. A code refused by every device tried counts as a failure on each of
    them: a wrong or throttled 6-digit code also delays the backup codes. An
    accepted code proves the user and clears the throttling of all their devices.
    """
    token = _normalize_otp(otp)
    models = (
        (TOTPDevice, StaticDevice)
        if TOTP_CODE_PATTERN.fullmatch(token)
        else (StaticDevice,)
    )
    for model in models:
        for device in model.objects.filter(user=user, confirmed=True).order_by("id"):
            if django_otp.verify_token(user, device.persistent_id, token) is not None:
                _clear_throttling(user)
                return True
    return False


def _clear_throttling(user: User) -> None:
    for model in (TOTPDevice, StaticDevice):
        model.objects.filter(user=user, confirmed=True).update(
            throttling_failure_timestamp=None, throttling_failure_count=0
        )


def login_mfa_outcome(*, user: User, otp) -> LoginMFAOutcome | MFAError:
    if settings.MFA_ENFORCEMENT == MFAEnforcement.OFF:
        return LoginMFAOutcome.GRANTED

    if has_confirmed_app(user):
        if not otp:
            return MFAError.REQUIRED
        if verify_otp(user=user, otp=otp):
            return LoginMFAOutcome.GRANTED
        return MFAError.INVALID

    if (
        settings.MFA_ENFORCEMENT == MFAEnforcement.REQUIRED
        or user.is_staff
        or user.is_superuser
        or user.groups.filter(name=settings.MFA_REQUIRED_GROUP_NAME).exists()
    ):
        return MFAError.SETUP_REQUIRED
    return LoginMFAOutcome.SETUP_SUGGESTED


def _lock_enrollment(user: User) -> None:
    """Lock the user row until the end of the transaction: setup and confirm of
    the same user run one after the other."""
    User.objects.select_for_update().get(pk=user.pk)


@transaction.atomic
def start_enrollment(user: User) -> TOTPDevice | MFAError:
    """Replace any abandoned enrollment with a new unconfirmed app.

    Refused once an app is confirmed: a stolen password must not replace it.
    """
    _lock_enrollment(user)
    if has_confirmed_app(user):
        return MFAError.ALREADY_CONFIGURED
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(user=user, name=APP_DEVICE_NAME, confirmed=False)


@transaction.atomic
def confirm_enrollment(*, user: User, otp) -> list[str] | MFAError:
    """Confirm the latest pending app with its first code and issue new backup codes.

    Returns the backup codes (readable only now), or the refusal.
    A refused code must not raise: the throttling failure it records would roll back.
    """
    _lock_enrollment(user)
    if has_confirmed_app(user):
        return MFAError.ALREADY_CONFIGURED
    device = (
        TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-id").first()
    )
    if device is None:
        return MFAError.SETUP_NOT_STARTED

    if django_otp.verify_token(user, device.persistent_id, _normalize_otp(otp)) is None:
        return MFAError.INVALID

    # A row deleted outside the user lock (TOTPDevice admin page) must not raise.
    if not TOTPDevice.objects.filter(pk=device.pk).update(confirmed=True):
        return MFAError.SETUP_NOT_STARTED
    codes = [StaticToken.random_token() for _ in range(BACKUP_CODES_COUNT)]
    StaticDevice.objects.filter(user=user).delete()
    backup_device = StaticDevice.objects.create(user=user, name=BACKUP_DEVICE_NAME)
    StaticToken.objects.bulk_create(
        StaticToken(device=backup_device, token=code) for code in codes
    )
    return codes


@transaction.atomic
def reset_mfa(user: User) -> None:
    """Delete the user's authenticator apps and backup codes, under the same lock as
    enrollment so a reset never deletes an app while it is being confirmed."""
    _lock_enrollment(user)
    TOTPDevice.objects.filter(user=user).delete()
    StaticDevice.objects.filter(user=user).delete()


def _normalize_otp(otp) -> str:
    return "".join(str(otp or "").split()).lower()
