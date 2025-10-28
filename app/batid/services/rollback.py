import uuid
from datetime import datetime

from django.contrib.auth.models import User
from django.db.models import Func

from batid.models import Building
from batid.services.RNB_team_user import get_RNB_team_user


class Lower(Func):
    function = "LOWER"
    arity = 1


def rollback(user: User, start_time: datetime, end_time: datetime):
    event_ids = get_user_events(user, start_time, end_time)
    user = get_RNB_team_user()
    for event_id in event_ids:
        Building.revert_event(user, {"source": "rollback"}, event_id)


def get_user_events(
    user: User, start_time: datetime, end_time: datetime
) -> list[uuid.UUID]:
    buildings = Building.objects.annotate(sys_period_lower=Lower("sys_period")).filter(
        sys_period_lower__gt=start_time,
        sys_period_lower__lt=end_time,
        user=user,
    )
    return list(set([b.event_id for b in buildings]))
