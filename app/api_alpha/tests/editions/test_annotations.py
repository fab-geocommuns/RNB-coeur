import uuid

from batid.models import EditionAnnotation
from batid.tests.factories.users import ContributorUserFactory, ReviewerUserFactory
from batid.tests.helpers import create_default_bdg
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


class EditionAnnotationViewTest(APITestCase):
    def setUp(self):
        self.reviewer = ReviewerUserFactory(username="reviewer_1")
        self.reviewee = ContributorUserFactory(username="reviewee_1")
        self.event_id = self._create_edition("AAAA1111BBBB", self.reviewee)

    # ----- helpers -----

    def _auth(self, user):
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

    def _create_edition(self, rnb_id, event_user=None):
        """Create a building carrying a fresh event_id and return that event_id."""
        bdg = create_default_bdg(rnb_id)
        bdg.event_id = uuid.uuid4()
        if event_user is not None:
            bdg.event_user = event_user
        bdg.save()
        return str(bdg.event_id)

    def _url(self, event_id):
        return f"/api/alpha/editions/{event_id}/annotations/"

    # ----- tests -----

    def test_non_reviewer_forbidden_reviewer_allowed(self):
        """
        Input: a contributor (not in the Reviewers group) and a reviewer both PUT an
        annotation on an existing edition.
        Expected: the contributor gets 403, the reviewer gets 201.
        """
        contributor = ContributorUserFactory(username="contrib_1")
        self._auth(contributor)
        r = self.client.put(
            self._url(self.event_id), {"status": "correct"}, format="json"
        )
        self.assertEqual(r.status_code, 403)

        self._auth(self.reviewer)
        r = self.client.put(
            self._url(self.event_id), {"status": "correct"}, format="json"
        )
        self.assertEqual(r.status_code, 201)

    def test_put_creates_then_updates(self):
        """
        Input: a reviewer PUTs twice on the same edition (correct, then incorrect).
        Expected: a single annotation exists for (event_id, reviewer); the second PUT
        updates it in place (200) and the stored status/comment reflect the last PUT.
        """
        self._auth(self.reviewer)

        r = self.client.put(
            self._url(self.event_id), {"status": "correct"}, format="json"
        )
        self.assertEqual(r.status_code, 201)

        r = self.client.put(
            self._url(self.event_id),
            {"status": "incorrect", "comment": "wrong shape"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)

        annotations = EditionAnnotation.objects.filter(
            event_id=self.event_id, reviewer=self.reviewer
        )
        self.assertEqual(annotations.count(), 1)
        self.assertEqual(annotations.first().status, "incorrect")
        self.assertEqual(annotations.first().comment, "wrong shape")
        self.assertEqual(annotations.first().reviewee, self.reviewee)

    def test_two_reviewers_distinct_annotations(self):
        """
        Input: two reviewers annotate the same edition.
        Expected: two distinct annotations are stored and GET returns both.
        """
        reviewer_2 = ReviewerUserFactory(username="reviewer_2")

        self._auth(self.reviewer)
        self.client.put(self._url(self.event_id), {"status": "correct"}, format="json")

        self._auth(reviewer_2)
        self.client.put(
            self._url(self.event_id), {"status": "uncertain"}, format="json"
        )

        r = self.client.get(self._url(self.event_id))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 2)
        reviewer_ids = {a["reviewer"]["id"] for a in data}
        self.assertEqual(reviewer_ids, {self.reviewer.id, reviewer_2.id})

    def test_comment_optional_and_independent_from_status(self):
        """
        Input: a PUT without comment, then a PUT with a comment on a "correct" status.
        Expected: both are accepted; comment is null when omitted and stored as-is with
        any status (no comment/status cross-validation).
        """
        self._auth(self.reviewer)

        r = self.client.put(
            self._url(self.event_id), {"status": "uncertain"}, format="json"
        )
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.json()["comment"])

        r = self.client.put(
            self._url(self.event_id),
            {"status": "correct", "comment": "looks fine but noting it"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["comment"], "looks fine but noting it")
        self.assertEqual(r.json()["status"], "correct")

    def test_self_annotation_allowed(self):
        """
        Input: a reviewer annotates an edition they authored (event_user == reviewer).
        Expected: the annotation is accepted (201).
        """
        event_id = self._create_edition("CCCC2222DDDD", event_user=self.reviewer)
        self._auth(self.reviewer)
        r = self.client.put(self._url(event_id), {"status": "correct"}, format="json")
        self.assertEqual(r.status_code, 201)

    def test_delete_removes_only_own_annotation(self):
        """
        Input: two reviewers annotate the same edition, then one DELETEs.
        Expected: only the current reviewer's annotation is removed (204); the other
        reviewer's annotation remains.
        """
        reviewer_2 = ReviewerUserFactory(username="reviewer_2")

        self._auth(self.reviewer)
        self.client.put(self._url(self.event_id), {"status": "correct"}, format="json")
        self._auth(reviewer_2)
        self.client.put(
            self._url(self.event_id), {"status": "incorrect"}, format="json"
        )

        self._auth(self.reviewer)
        r = self.client.delete(self._url(self.event_id))
        self.assertEqual(r.status_code, 204)

        remaining = EditionAnnotation.objects.filter(event_id=self.event_id)
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.first().reviewer_id, reviewer_2.id)

    def test_unknown_event_id_returns_404(self):
        """
        Input: a reviewer PUTs (and GETs) an annotation on an event_id that no building
        carries.
        Expected: 404 on both methods.
        """
        unknown_event_id = str(uuid.uuid4())
        self._auth(self.reviewer)

        r = self.client.put(
            self._url(unknown_event_id), {"status": "correct"}, format="json"
        )
        self.assertEqual(r.status_code, 404)

        r = self.client.get(self._url(unknown_event_id))
        self.assertEqual(r.status_code, 404)
