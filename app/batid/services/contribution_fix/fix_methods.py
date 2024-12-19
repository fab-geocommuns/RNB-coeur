from django.db import transaction

from batid.exceptions import ContributionFixTooBroad
from batid.models import Building
from batid.models import Contribution


def _fix_contributions_with_action(
    user, contribution_message, contribution_email, review_comment, review_action
):
    """perform an action on all the buildings linked to the corresponding contributions"""
    if not contribution_message and not contribution_email:
        raise ContributionFixTooBroad(
            "you cannot perform a contribution fix without specifying a message or an email."
        )

    contributions = Contribution.objects.filter(status="pending")

    if contribution_message:
        contributions = contributions.filter(text=contribution_message)
    if contribution_email:
        contributions = contributions.filter(email=contribution_email)

    with transaction.atomic():
        for contribution in contributions:
            contribution.fix(user, review_comment)
            review_action(contribution)


def fix_contributions_deactivate(
    user, contribution_message, contribution_email, review_comment
):
    def review_action_deactivate(contribution):
        event_origin = {"source": "contribution", "contribution_id": contribution.id}
        building = Building.objects.get(rnb_id=contribution.rnb_id)
        building.deactivate(user, event_origin)

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

    _fix_contributions_with_action(
        user,
        contribution_message,
        contribution_email,
        review_comment,
        review_action_demolish,
    )
