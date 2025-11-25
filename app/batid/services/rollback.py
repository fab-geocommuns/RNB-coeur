import uuid
from datetime import datetime

from django.contrib.auth.models import User
from django.db.models import Func

from batid.exceptions import RevertNotAllowed
from batid.models import Building
from batid.models.building import BuildingWithHistory
from batid.models.others import DataFix
from batid.services.RNB_team_user import get_RNB_team_user


class RangeLower(Func):
    function = "lower"
    arity = 1


def rollback(user: User, start_time: datetime | None, end_time: datetime | None):
    team_rnb = get_RNB_team_user()

    data_fix = DataFix.objects.create(
        text=f"Rollback des éditions faites par {user.username} (email : {user.email}, id : {user.id}) entre les dates {start_time} et {end_time}",  # type: ignore[attr-defined]
        user=team_rnb,
    )
    event_ids = get_user_events(user, start_time, end_time)
    events_reverted = []
    events_not_revertable = []
    events_already_reverted = []
    events_are_revert = []

    for event_id in event_ids:
        try:
            if event_id:
                if Building.event_has_been_reverted(event_id):
                    events_already_reverted.append(event_id)
                elif Building.event_is_a_revert(event_id):
                    events_are_revert.append(event_id)
                else:
                    revert_uuid = Building.revert_event(
                        {"source": "data_fix", "id": data_fix.id},  # type: ignore[attr-defined]
                        event_id,
                        user_making_revert=team_rnb,
                    )
                    if revert_uuid:
                        events_reverted.append(event_id)
        except RevertNotAllowed:
            events_not_revertable.append(event_id)

    return {
        "user": user.username,
        "data_fix_id": data_fix.id,  # type: ignore[attr-defined]
        "events_found_n": len(event_ids),
        "start_time": start_time,
        "end_time": end_time,
        "events_reverted": events_reverted,
        "events_reverted_n": len(events_reverted),
        "events_not_revertable": events_not_revertable,
        "events_not_revertable_n": len(events_not_revertable),
        "events_already_reverted": events_already_reverted,
        "events_already_reverted_n": len(events_already_reverted),
        "events_are_revert": events_are_revert,
        "events_are_revert_n": len(events_are_revert),
    }


def rollback_dry_run(
    user: User, start_time: datetime | None, end_time: datetime | None
):
    event_ids = get_user_events(user, start_time, end_time)

    events_n = len(event_ids)
    events_not_revertable = []
    events_revertable = []
    events_already_reverted = []
    events_are_revert = []

    for event_id in event_ids:
        if event_id:
            if Building.event_has_been_reverted(event_id):
                events_already_reverted.append(event_id)
            elif Building.event_is_a_revert(event_id):
                events_are_revert.append(event_id)
            elif Building.event_could_be_reverted(event_id, end_time=end_time):
                events_revertable.append(event_id)
            else:
                events_not_revertable.append(event_id)

    return {
        "user": user.username,
        "events_found_n": events_n,
        "start_time": start_time,
        "end_time": end_time,
        "events_revertable": events_revertable,
        "events_revertable_n": len(events_revertable),
        "events_not_revertable": events_not_revertable,
        "events_not_revertable_n": len(events_not_revertable),
        "events_already_reverted": events_already_reverted,
        "events_already_reverted_n": len(events_already_reverted),
        "events_are_revert": events_are_revert,
        "events_are_revert_n": len(events_are_revert),
    }


def get_user_events(
    user: User, start_time: datetime | None, end_time: datetime | None
) -> list[uuid.UUID | None]:
    buildings = (
        BuildingWithHistory.objects.annotate(sys_period_lower=RangeLower("sys_period"))
        .filter(event_user=user)
        .order_by("-sys_period")
    )
    if start_time:
        buildings = buildings.filter(sys_period_lower__gte=start_time)

    if end_time:
        buildings = buildings.filter(sys_period_lower__lte=end_time)

    # print([(b.event_id, b.sys_period) for b in buildings])

    # remove duplicates while preserving order
    return list(dict.fromkeys([b.event_id for b in buildings]))
