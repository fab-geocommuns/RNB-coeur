import datetime
from unittest import mock

from batid.models import Trophy
from batid.tests.factories.users import ContributorUserFactory
from rest_framework.test import APITestCase


def _award(user, trophy_type, level, unlocked_at=None):
    """Create a Trophy for `user`; force level_unlocked_at to `unlocked_at` when given
    (the field is auto_now_add, hence the post-create UPDATE)."""
    trophy = Trophy.objects.create(user=user, trophy_type=trophy_type, level=level)
    if unlocked_at is not None:
        Trophy.objects.filter(id=trophy.id).update(level_unlocked_at=unlocked_at)
    return trophy


class UserTrophiesViewTest(APITestCase):
    def setUp(self):
        self.user = ContributorUserFactory(username="winner")
        self.other = ContributorUserFactory(username="other")

    def test_lists_trophies_most_recent_first(self):
        """
        Input: user has 3 trophies unlocked on distinct dates.
        Expected: 200; a list of the 3 trophies ordered by unlocked_at descending,
        each with label, level and unlocked_at.
        """
        d1 = datetime.datetime(2026, 6, 1, 10, 0, tzinfo=datetime.timezone.utc)
        d2 = datetime.datetime(2026, 6, 10, 10, 0, tzinfo=datetime.timezone.utc)
        d3 = datetime.datetime(2026, 6, 20, 10, 0, tzinfo=datetime.timezone.utc)
        _award(self.user, "validateur", 1, d1)
        _award(self.user, "course_de_fond", 1, d3)
        _award(self.user, "validateur", 2, d2)

        r = self.client.get(f"/api/alpha/user/{self.user.username}/trophies/")

        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(
            [(t["trophy"], t["level"]) for t in body],
            [("course_de_fond", 1), ("validateur", 2), ("validateur", 1)],
        )
        self.assertIn("unlocked_at", body[0])

    def test_includes_trophy_and_level_labels(self):
        """
        Input: user has the 'course_de_fond' level 1 trophy.
        Expected: 200; the trophy carries trophy='course_de_fond',
        trophy_label='Course de fond', level=1, level_label='bronze'.
        """

        _award(self.user, "course_de_fond", 1)

        r = self.client.get(f"/api/alpha/user/{self.user.username}/trophies/")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json()[0],
            {
                "trophy": "course_de_fond",
                "trophy_label": "Course de fond",
                "level": 1,
                "level_label": "bronze",
                "unlocked_at": mock.ANY,
            },
        )

    def test_only_returns_the_requested_users_trophies(self):
        """
        Input: the requested user has 1 trophy, another user has 1 trophy.
        Expected: 200; only the requested user's trophy is returned.
        """
        _award(self.user, "validateur", 1)
        _award(self.other, "superv", 1)

        r = self.client.get(f"/api/alpha/user/{self.user.username}/trophies/")

        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["trophy"], "validateur")

    def test_user_without_trophies_returns_empty_list(self):
        """Input: an existing user with no trophy. Expected: 200 with an empty list."""
        r = self.client.get(f"/api/alpha/user/{self.user.username}/trophies/")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_unknown_user_returns_404(self):
        """Input: a username that does not exist. Expected: 404."""
        r = self.client.get("/api/alpha/user/does_not_exist/trophies/")

        self.assertEqual(r.status_code, 404)
