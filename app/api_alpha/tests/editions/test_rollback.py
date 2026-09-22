import uuid

from batid.models.building import Building, EventType
from batid.models.others import DataFix
from batid.tests.factories.users import (
    ContributorUserFactory,
    ReviewerUserFactory,
    RollbackUserFactory,
)
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITransactionTestCase


@override_settings(MAX_BUILDING_AREA=float("inf"))
class RollbackEventViewTest(APITransactionTestCase):
    """
    Uses APITransactionTestCase (not APITestCase) because reverting an event goes
    through the batid_building_with_history DB triggers, which need a real
    transaction to behave correctly (same reason batid/tests/test_rollback.py uses
    TransactionTestCase).
    """

    def setUp(self):
        # the RNB team system user: revert events are always authored by this user,
        # see batid.services.rollback.rollback_event
        User.objects.create_user(username="RNB")

        self.rollback_user = RollbackUserFactory(username="rollback_1")
        self.reviewer = ReviewerUserFactory(username="reviewer_1")
        self.author = ContributorUserFactory(username="author_1")

        self.building = Building.create_new(
            user=self.author,
            event_origin={"source": "contribution"},
            status="constructed",
            addresses_id=[],
            shape=GEOSGeometry("POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))"),
            ext_ids=[],
        )
        self.creation_event_id = str(self.building.event_id)

    # ----- helpers -----

    def _auth(self, user):
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

    def _url(self, event_id):
        return f"/api/alpha/editions/{event_id}/rollback/"

    def _post(self, event_id, comment="This edition looks wrong"):
        body = {} if comment is None else {"comment": comment}
        return self.client.post(self._url(event_id), body, format="json")

    # ----- tests -----

    def test_reviewer_without_rollback_group_forbidden(self):
        """
        Input: a reviewer who is not in the Rollback group POSTs a rollback.
        Expected: 403. Being a Reviewer is only what shows the button in the UI, the
        API call itself needs the Rollback group.
        """
        self._auth(self.reviewer)
        r = self._post(self.creation_event_id)
        self.assertEqual(r.status_code, 403)

    def test_contributor_forbidden(self):
        """
        Input: a plain contributor (neither reviewer nor rollback) POSTs a rollback.
        Expected: 403.
        """
        self._auth(self.author)
        r = self._post(self.creation_event_id)
        self.assertEqual(r.status_code, 403)

    def test_rollback_user_reverts_event(self):
        """
        Input: a user in the Rollback group POSTs a rollback of a creation event
        with a comment.
        Expected: 200, the response carries the new revert_event_id and a
        data_fix_id, a DataFix is created whose text carries the actor and the
        comment, and the building is deactivated with a revert_creation event type.
        """
        self._auth(self.rollback_user)
        r = self._post(self.creation_event_id, comment="This edition looks wrong")
        self.assertEqual(r.status_code, 200)

        data = r.json()
        self.assertEqual(data["event_id"], self.creation_event_id)
        self.assertIsNotNone(data["revert_event_id"])
        self.assertNotEqual(data["revert_event_id"], self.creation_event_id)
        self.assertIsNotNone(data["data_fix_id"])

        data_fix = DataFix.objects.get(id=data["data_fix_id"])
        self.assertIn(self.creation_event_id, data_fix.text)
        self.assertIn(self.rollback_user.username, data_fix.text)
        self.assertIn("This edition looks wrong", data_fix.text)

        self.building.refresh_from_db()
        self.assertFalse(self.building.is_active)
        self.assertEqual(self.building.event_type, EventType.REVERT_CREATION.value)
        self.assertEqual(str(self.building.revert_event_id), self.creation_event_id)

    def test_missing_comment_returns_400(self):
        """
        Input: a rollback user POSTs without a comment field.
        Expected: 400, a comment is required (same requirement as the front-end,
        where the rollback button stays disabled until a comment is written).
        """
        self._auth(self.rollback_user)
        r = self._post(self.creation_event_id, comment=None)
        self.assertEqual(r.status_code, 400)

    def test_blank_comment_returns_400(self):
        """
        Input: a rollback user POSTs a comment made only of whitespace.
        Expected: 400, a blank comment doesn't satisfy the requirement.
        """
        self._auth(self.rollback_user)
        r = self._post(self.creation_event_id, comment="   ")
        self.assertEqual(r.status_code, 400)

    def test_already_reverted_returns_400(self):
        """
        Input: the same event is rolled back twice.
        Expected: the first call succeeds (200), the second is rejected (400) since
        the event has already been reverted.
        """
        self._auth(self.rollback_user)
        r = self._post(self.creation_event_id)
        self.assertEqual(r.status_code, 200)

        r = self._post(self.creation_event_id)
        self.assertEqual(r.status_code, 400)

    def test_rollback_of_a_revert_returns_400(self):
        """
        Input: rollback a creation event, then try to rollback the resulting revert
        event itself.
        Expected: 400, a revert cannot be reverted.
        """
        self._auth(self.rollback_user)
        r = self._post(self.creation_event_id)
        self.assertEqual(r.status_code, 200)
        revert_event_id = r.json()["revert_event_id"]

        r = self._post(revert_event_id)
        self.assertEqual(r.status_code, 400)

    def test_unknown_event_id_returns_404(self):
        """
        Input: a rollback user POSTs to an event_id no building carries.
        Expected: 404.
        """
        self._auth(self.rollback_user)
        r = self._post(str(uuid.uuid4()))
        self.assertEqual(r.status_code, 404)
