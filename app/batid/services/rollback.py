import uuid
from datetime import datetime

from batid.exceptions import DatabaseInconsistency, RevertNotAllowed
from batid.models.building import BuildingWithHistory, Event, EventType
from batid.models.others import DataFix
from batid.services.RNB_team_user import get_RNB_team_user
from django.contrib.auth.models import User
from django.db.models import Func


class RangeLower(Func):
    function = "lower"
    arity = 1


def _prefetch_event_data(event_ids: list) -> tuple[dict, set]:
    """
    Pre-fetch building data for all event_ids in two bulk queries
    instead of one query per event (avoids N+1).

    Returns:
        one_building_by_event_id: dict mapping event_id -> one BuildingWithHistory (arbitrary when multiple buildings share the same event)
        already_reverted_ids: set of event_ids that have already been reverted
    """
    one_building_by_event_id = {
        b.event_id: b
        for b in BuildingWithHistory.objects.filter(event_id__in=event_ids)
    }
    already_reverted_ids = set(
        BuildingWithHistory.objects.filter(revert_event_id__in=event_ids).values_list(
            "revert_event_id", flat=True
        )
    )
    return one_building_by_event_id, already_reverted_ids


def _check_incoherent_event(building) -> None:
    """Raises DatabaseInconsistency for old-style reactivations lacking revert_event_id."""
    if (
        building
        and building.event_type == EventType.REACTIVATION.value
        and not building.revert_event_id
    ):
        raise DatabaseInconsistency(
            """This is unlucky: you are trying to rollback a deactivation/reactivation
            made before the revert_event_id field existed and this could damage the database.
            The solution is to disable the DB trigger and manually populate the revert_event_id field
            of the reactivation (with the event_id of the corresponding deactivation), and then try again.
            """
        )


def rollback(user: User, start_time: datetime | None, end_time: datetime | None):
    team_rnb = get_RNB_team_user()

    data_fix = DataFix.objects.create(
        text=f"Rollback des éditions faites par {user.username} (email : {user.email}, id : {user.id}) entre les dates {start_time} et {end_time}",  # type: ignore[attr-defined]
        user=team_rnb,
    )
    event_ids = get_user_events(user, start_time, end_time)

    # Pre-fetch in bulk to avoid N+1 (3 queries/event → 2 bulk queries)
    one_building_by_event_id, already_reverted_ids = _prefetch_event_data(event_ids)

    events_reverted = []
    events_not_revertable = []
    events_already_reverted = []
    events_are_revert = []

    for event_id in event_ids:
        try:
            if event_id:
                building = one_building_by_event_id.get(event_id)
                _check_incoherent_event(building)

                if event_id in already_reverted_ids:
                    events_already_reverted.append(event_id)
                elif building and building.revert_event_id is not None:
                    events_are_revert.append(event_id)
                else:
                    revert_uuid = Event.revert_event(
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

    # Pre-fetch in bulk to avoid N+1 (3 queries/event → 2 bulk queries)
    one_building_by_event_id, already_reverted_ids = _prefetch_event_data(event_ids)

    events_n = len(event_ids)
    events_not_revertable = []
    events_revertable = []
    events_already_reverted = []
    events_are_revert = []

    for event_id in event_ids:
        if event_id:
            building = one_building_by_event_id.get(event_id)
            _check_incoherent_event(building)

            if event_id in already_reverted_ids:
                events_already_reverted.append(event_id)
            elif building and building.revert_event_id is not None:
                events_are_revert.append(event_id)
            elif Event.event_could_be_reverted(event_id, end_time=end_time):
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
    qs = (
        BuildingWithHistory.objects.annotate(sys_period_lower=RangeLower("sys_period"))
        .filter(event_user=user)
        .order_by("-sys_period")
        .values_list("event_id", flat=True)
    )
    if start_time:
        qs = qs.filter(sys_period_lower__gte=start_time)

    if end_time:
        qs = qs.filter(sys_period_lower__lte=end_time)

    # remove duplicates while preserving order
    return list(dict.fromkeys(qs))
