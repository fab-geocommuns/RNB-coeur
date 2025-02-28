from django.db import transaction

from batid.exceptions import ContributionFixTooBroad
from batid.models import Building
from batid.models import Contribution


def _fix_contributions_with_action(
    user, contribution_message, contribution_email, review_comment, review_action
):
    """perform an action on all the buildings linked to the corresponding contributions"""
    if not contribution_message or not contribution_email:
        raise ContributionFixTooBroad(
            "you cannot perform a contribution fix without specifying a message and an email"
        )

    contributions = (
        Contribution.objects.filter(status="pending")
        .filter(text=contribution_message)
        .filter(email=contribution_email)
        .order_by("created_at")
    )

    with transaction.atomic():
        for contribution in contributions:
            fixed = review_action(contribution)
            if fixed:
                contribution.fix(user, review_comment)


def fix_contributions_deactivate(
    user, contribution_message, contribution_email, review_comment
):
    def review_action_deactivate(contribution):
        event_origin = {"source": "contribution", "contribution_id": contribution.id}
        building = Building.objects.get(rnb_id=contribution.rnb_id)
        building.deactivate(user, event_origin)
        return True

    _fix_contributions_with_action(
        user,
        contribution_message,
        contribution_email,
        review_comment,
        review_action_deactivate,
    )


def fix_contributions_demolish(
    user, contribution_message, contribution_email, review_comment
):
    def review_action_demolish(contribution):
        event_origin = {"source": "contribution", "contribution_id": contribution.id}
        building = Building.objects.get(rnb_id=contribution.rnb_id)
        building.update(user, event_origin, status="demolished", addresses_id=None)
        return True

    _fix_contributions_with_action(
        user,
        contribution_message,
        contribution_email,
        review_comment,
        review_action_demolish,
    )


def fix_contributions_merge_if_obvious(
    user, contribution_message, contribution_email, review_comment
):
    def review_action_merge(contribution):
        event_origin = {"source": "contribution", "contribution_id": contribution.id}
        building = Building.objects.get(rnb_id=contribution.rnb_id)

        if not building.is_active:
            return False

        neighbor_buildings = (
            Building.objects.filter(shape__intersects=building.shape)
            .filter(is_active=True)
            .exclude(rnb_id=building.rnb_id)
            .all()
        )

        if len(neighbor_buildings) == 1:
            neighbor = neighbor_buildings[0]
            Building.merge(
                [building, neighbor],
                user,
                event_origin,
                status=building.status,
                addresses_id=list(
                    set((building.addresses_id or []) + (neighbor.addresses_id or []))
                ),
            )
            return True
        else:
            return False

    _fix_contributions_with_action(
        user,
        contribution_message,
        contribution_email,
        review_comment,
        review_action_merge,
    )
