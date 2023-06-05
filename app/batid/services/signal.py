from batid.models import Building, Organization, Signal
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from app.celery import app


def create_signal(
    type: str,
    building: Building,
    origin,
    creator: User = None,
    send_task: bool = True,
) -> Signal:
    org = _convert_user_to_org(creator)

    signal_data = {
        "type": type,
        "building": building,
        "origin": _convert_signal_origin(origin),
        "creator_copy_id": creator.pk if creator else None,
        "creator_copy_fname": creator.first_name if creator else None,
        "creator_copy_lname": creator.last_name if creator else None,
        "creator_org_copy_id": org.pk if org else None,
        "creator_org_copy_name": org.name if org else None,
    }

    s = Signal.objects.create(**signal_data)
    if send_task:
        app.send_task("tasks.handle_signal", args=[s.pk])

    return s


def _convert_signal_origin(origin) -> str:
    if isinstance(origin, str):
        return origin
    elif isinstance(origin, models.Model):
        return f"{origin.__class__.__name__}:{origin.pk}"

    return ""


def _convert_user_to_org(user: User) -> Organization:
    if user is None:
        return None

    if user.organizations.count() == 1:
        return user.organizations.first()

    return None
