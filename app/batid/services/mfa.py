import re
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

import django_otp
from batid.services.brevo import BrevoTemplate, send_transactional_email
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.authtoken.models import Token

from app.mfa_enforcement import MFAEnforcement

APP_DEVICE_NAME = "Application d'authentification"
BACKUP_DEVICE_NAME = "Codes de secours"
BACKUP_CODES_COUNT = 10

NUMERIC_CODE_PATTERN = re.compile(r"[0-9]+")

PARIS_TZ = ZoneInfo("Europe/Paris")


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


class MFAChange(StrEnum):
    """Changes of the second factor emailed to the account owner."""

    APP_ACTIVATED = "app_activated"
    APP_REPLACED = "app_replaced"
    BACKUP_CODES_REGENERATED = "backup_codes_regenerated"


_CHANGE_SUBJECTS = {
    MFAChange.APP_ACTIVATED: "Double authentification activée sur votre compte RNB",
    MFAChange.APP_REPLACED: "Application d'authentification changée sur votre compte RNB",
    MFAChange.BACKUP_CODES_REGENERATED: "Codes de secours régénérés sur votre compte RNB",
}

_CHANGE_TEXTS = {
    MFAChange.APP_ACTIVATED: "La double authentification a été activée sur votre compte.",
    MFAChange.APP_REPLACED: (
        "L'application d'authentification de votre compte a été remplacée. "
        "Vos anciens codes de secours ne fonctionnent plus."
    ),
    MFAChange.BACKUP_CODES_REGENERATED: (
        "De nouveaux codes de secours ont été générés pour votre compte. "
        "Les anciens ne fonctionnent plus."
    ),
}


def has_confirmed_app(user: User) -> bool:
    """Backup codes alone do not count: only a confirmed authenticator app does."""
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def verify_otp(*, user: User, otp) -> bool:
    """Check a code against the user's confirmed devices, oldest first, until one
    accepts it: a numeric code goes to the authenticator apps expecting its length
    (6 digits, or 8 if set in the admin), then to the backup codes (staff can add
    numeric ones with `addstatictoken`); any other code goes to the backup codes
    only.

    Each device keeps its own throttling, so wrong backup codes never delay TOTP
    codes. A code refused by every device tried counts as a failure on each of
    them: a wrong or throttled app code also delays the backup codes. An
    accepted code proves the user and clears the throttling of all their devices.
    """
    token = _normalize_otp(otp)
    # No code holds a control or surrogate character, and the database refuses them.
    if not token.isprintable():
        return False
    confirmed = {"user": user, "confirmed": True}
    backup_devices = StaticDevice.objects.filter(**confirmed)
    candidates: tuple[QuerySet, ...] = (
        (TOTPDevice.objects.filter(**confirmed, digits=len(token)), backup_devices)
        if NUMERIC_CODE_PATTERN.fullmatch(token)
        else (backup_devices,)
    )
    for devices in candidates:
        for device in devices.order_by("id"):
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
    ):
        return MFAError.SETUP_REQUIRED
    return LoginMFAOutcome.SETUP_SUGGESTED


def _lock_enrollment(user: User) -> None:
    """Lock the user row until the end of the transaction: enrollment, replacement
    and regeneration of the same user run one after the other."""
    User.objects.select_for_update().get(pk=user.pk)


@transaction.atomic
def start_enrollment(user: User) -> TOTPDevice | MFAError:
    """Replace any abandoned enrollment with a new unconfirmed app.

    Refused once an app is confirmed: a stolen password must not replace it.
    """
    _lock_enrollment(user)
    if has_confirmed_app(user):
        return MFAError.ALREADY_CONFIGURED
    return _create_pending_app(user)


@transaction.atomic
def confirm_enrollment(*, user: User, otp) -> list[str] | MFAError:
    """Confirm the latest pending app with its first code, issue new backup codes
    and revoke the API token: one obtained with the password alone stops working.

    Returns the backup codes (readable only now), or the refusal.
    """
    _lock_enrollment(user)
    if has_confirmed_app(user):
        return MFAError.ALREADY_CONFIGURED
    device = _confirm_pending_app(user=user, otp=otp)
    if isinstance(device, MFAError):
        return device
    codes = _issue_backup_codes(user)
    Token.objects.filter(user=user).delete()
    _notify_owner_after_commit(user=user, change=MFAChange.APP_ACTIVATED)
    return codes


@transaction.atomic
def start_replacement(*, user: User, otp) -> TOTPDevice | MFAError:
    """Create a new unconfirmed app once the current second factor is proven, by a
    code of the confirmed app or a backup code. The confirmed app keeps working
    until the new one is confirmed with `confirm_replacement`."""
    _lock_enrollment(user)
    refusal = _current_factor_refusal(user=user, otp=otp)
    return refusal or _create_pending_app(user)


@transaction.atomic
def confirm_replacement(*, user: User, otp) -> list[str] | MFAError:
    """Confirm the latest pending app with its first code, delete the other apps and
    issue new backup codes. The API token is kept: the replacement changes the
    second factor, not the API key, and was started with the password and the
    current second factor.

    Returns the backup codes (readable only now), or the refusal.
    """
    _lock_enrollment(user)
    # Without a confirmed app, this would finish a first enrollment without
    # revoking the token issued with the password alone.
    if not has_confirmed_app(user):
        return MFAError.SETUP_NOT_STARTED
    device = _confirm_pending_app(user=user, otp=otp)
    if isinstance(device, MFAError):
        return device
    TOTPDevice.objects.filter(user=user).exclude(pk=device.pk).delete()
    _notify_owner_after_commit(user=user, change=MFAChange.APP_REPLACED)
    return _issue_backup_codes(user)


@transaction.atomic
def regenerate_backup_codes(*, user: User, otp) -> list[str] | MFAError:
    """Replace the backup codes once the current second factor is proven."""
    _lock_enrollment(user)
    refusal = _current_factor_refusal(user=user, otp=otp)
    if refusal:
        return refusal
    _notify_owner_after_commit(user=user, change=MFAChange.BACKUP_CODES_REGENERATED)
    return _issue_backup_codes(user)


def _notify_owner_after_commit(*, user: User, change: MFAChange) -> None:
    """Queue the email to the owner once the change is saved: a change they did not
    make is noticed now, not at their next login."""
    from batid.tasks import send_mfa_change_notification

    user_id = user.pk
    # Taken now: a delayed or retried task must still show when the change happened.
    changed_at = timezone.now().isoformat()
    # robust: a broker outage must not turn an already saved change into a 500.
    transaction.on_commit(
        lambda: send_mfa_change_notification.delay(
            user_id=user_id, change=change, changed_at=changed_at
        ),
        robust=True,
    )


def notify_mfa_change(*, user_id: int, change: MFAChange, changed_at: datetime) -> None:
    """Email the account owner about the change through Brevo, with the account and
    the time of the change so they can tell whether it was them. Security email: no
    opt-out. Skipped for an account without email."""
    user = User.objects.get(pk=user_id)
    if not user.email:
        return
    send_transactional_email(
        template=BrevoTemplate.MFA_CHANGE,
        to=user.email,
        params={
            "SUBJECT": _CHANGE_SUBJECTS[change],
            "CHANGE_TEXT": _CHANGE_TEXTS[change],
            "ACCOUNT": user.username,
            "CHANGED_AT": _paris_time(changed_at),
            "PASSWORD_RESET_URL": f"{settings.FRONTEND_URL}/auth/mdp-oublie",
        },
    )


def _paris_time(moment: datetime) -> str:
    local = moment.astimezone(PARIS_TZ)
    return f"{local:%d/%m/%Y} à {local:%H} h {local:%M} (heure de Paris)"


def _current_factor_refusal(*, user: User, otp) -> MFAError | None:
    # The app check comes first: a backup code of an account without app is not
    # consumed.
    if not has_confirmed_app(user):
        return MFAError.SETUP_NOT_STARTED
    if not verify_otp(user=user, otp=otp):
        return MFAError.INVALID
    return None


def _create_pending_app(user: User) -> TOTPDevice:
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(user=user, name=APP_DEVICE_NAME, confirmed=False)


def _confirm_pending_app(*, user: User, otp) -> TOTPDevice | MFAError:
    """Confirm the latest pending app with its first code.

    A refused code must not raise: the throttling failure it records would roll back.
    """
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
    return device


def _issue_backup_codes(user: User) -> list[str]:
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
