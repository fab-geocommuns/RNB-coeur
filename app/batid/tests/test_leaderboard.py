import datetime
import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.core.mail import EmailMultiAlternatives
from django.test import override_settings
from django.test import TestCase

from batid.models.building import Building
from batid.services.email import build_monthly_leaderboard_email
from batid.services.leaderboard import get_monthly_edit_leaderboard
from batid.services.leaderboard import get_monthly_new_users
from batid.tests.factories.users import ContributorUserFactory

SIMPLE_POLYGON = GEOSGeometry(
    json.dumps(
        {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 0.001], [0.001, 0.001], [0.001, 0], [0, 0]]],
        }
    )
)

OTHER_POLYGON = GEOSGeometry(
    json.dumps(
        {
            "type": "Polygon",
            "coordinates": [[[1, 1], [1, 1.001], [1.001, 1.001], [1.001, 1], [1, 1]]],
        }
    )
)


@override_settings(MAX_BUILDING_AREA=float("inf"))
class LeaderboardQueryTestCase(TestCase):
    def test_leaderboard_counts_distinct_events(self):
        """
        Input: user A creates 1 building then updates it (2 contribution events); user B creates 1 building (1 contribution event).
        Expected: user A has edit_count=2, user B has edit_count=1, ordered desc.
        """
        user_a = ContributorUserFactory(username="user_a", email="a@example.com")
        user_b = ContributorUserFactory(username="user_b", email="b@example.com")

        b1 = Building.create_new(
            user=user_a,
            event_origin={"source": "contribution"},
            status="constructed",
            addresses_id=[],
            shape=SIMPLE_POLYGON,
            ext_ids=[],
        )
        b1.update(
            user=user_a,
            event_origin={"source": "contribution"},
            status="demolished",
            addresses_id=None,
            shape=None,
        )
        Building.create_new(
            user=user_b,
            event_origin={"source": "contribution"},
            status="constructed",
            addresses_id=[],
            shape=OTHER_POLYGON,
            ext_ids=[],
        )

        today = datetime.date.today()
        results = get_monthly_edit_leaderboard(today.year, today.month)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["username"], "user_a")
        self.assertEqual(results[0]["edit_count"], 2)
        self.assertEqual(results[1]["username"], "user_b")
        self.assertEqual(results[1]["edit_count"], 1)

    def test_leaderboard_excludes_other_months(self):
        """
        Input: 1 building created now (current month) with source=contribution.
        Expected: current month query returns 1 result; next month query returns 0.
        """
        user = ContributorUserFactory(username="user_c", email="c@example.com")
        Building.create_new(
            user=user,
            event_origin={"source": "contribution"},
            status="constructed",
            addresses_id=[],
            shape=SIMPLE_POLYGON,
            ext_ids=[],
        )

        today = datetime.date.today()
        results = get_monthly_edit_leaderboard(today.year, today.month)
        self.assertEqual(len(results), 1)

        next_year = today.year if today.month < 12 else today.year + 1
        next_month = today.month + 1 if today.month < 12 else 1
        results_next = get_monthly_edit_leaderboard(next_year, next_month)
        self.assertEqual(len(results_next), 0)

    def test_leaderboard_excludes_non_contribution_source(self):
        """
        Input: 1 building created by a logged-in user with event_origin source != 'contribution'.
        Expected: leaderboard is empty (non-contribution edits are excluded).
        """
        user = ContributorUserFactory(username="user_import", email="import@example.com")
        Building.create_new(
            user=user,
            event_origin={"source": "import"},
            status="constructed",
            addresses_id=[],
            shape=SIMPLE_POLYGON,
            ext_ids=[],
        )

        today = datetime.date.today()
        results = get_monthly_edit_leaderboard(today.year, today.month)
        self.assertEqual(len(results), 0)

    def test_leaderboard_excludes_null_event_user(self):
        """
        Input: 1 building created without a user (import source).
        Expected: leaderboard is empty.
        """
        Building.create_new(
            user=None,
            event_origin={"source": "import"},
            status="constructed",
            addresses_id=[],
            shape=SIMPLE_POLYGON,
            ext_ids=[],
        )

        today = datetime.date.today()
        results = get_monthly_edit_leaderboard(today.year, today.month)
        self.assertEqual(len(results), 0)

    def test_get_monthly_new_users(self):
        """
        Input: user A joined this month (default), user B's date_joined set to last month.
        Expected: this month query returns user A only; last month query returns user B only.
        """
        user_a = User.objects.create_user(username="user_d", email="d@example.com")
        user_b = User.objects.create_user(username="user_e", email="e@example.com")

        today = datetime.date.today()
        last_year = today.year if today.month > 1 else today.year - 1
        last_month = today.month - 1 if today.month > 1 else 12
        last_month_date = datetime.datetime(
            last_year, last_month, 15, tzinfo=datetime.timezone.utc
        )
        User.objects.filter(pk=user_b.pk).update(date_joined=last_month_date)

        this_month_users = get_monthly_new_users(today.year, today.month)
        self.assertIn(user_a, this_month_users)
        self.assertNotIn(user_b, this_month_users)

        last_month_users = get_monthly_new_users(last_year, last_month)
        self.assertNotIn(user_a, last_month_users)
        self.assertIn(user_b, last_month_users)


class LeaderboardEmailTestCase(TestCase):
    @override_settings(
        RNB_SEND_ADDRESS="rnb@example.com",
        RNB_REPLY_TO_ADDRESS="reply@example.com",
    )
    def test_build_monthly_leaderboard_email(self):
        """
        Input: leaderboard with one entry (alice, 5 edits) and a recipient email.
        Expected: EmailMultiAlternatives with subject and HTML body containing month label,
        username, and edit count.
        """
        leaderboard = [{"username": "alice", "edit_count": 5}]
        email = build_monthly_leaderboard_email(
            leaderboard, "janvier 2026", "recipient@example.com"
        )

        self.assertIsInstance(email, EmailMultiAlternatives)
        self.assertIn("janvier 2026", email.subject)
        html_body = email.alternatives[0][0]
        self.assertIn("alice", html_body)
        self.assertIn("5", html_body)
        self.assertIn("janvier 2026", html_body)
        self.assertEqual(email.to, ["recipient@example.com"])

    @override_settings(
        RNB_SEND_ADDRESS="rnb@example.com",
        RNB_REPLY_TO_ADDRESS="reply@example.com",
    )
    def test_build_monthly_leaderboard_email_with_new_users(self):
        """
        Input: leaderboard with one entry, plus two new usernames.
        Expected: HTML body contains "Bienvenue aux nouveaux inscrits" and both new usernames.
        """
        leaderboard = [{"username": "alice", "edit_count": 5}]
        new_usernames = ["bob", "charlie"]
        email = build_monthly_leaderboard_email(
            leaderboard, "février 2026", "recipient@example.com", new_usernames
        )

        html_body = email.alternatives[0][0]
        self.assertIn("Bienvenue aux nouveaux inscrits", html_body)
        self.assertIn("bob", html_body)
        self.assertIn("charlie", html_body)

    @override_settings(
        RNB_SEND_ADDRESS="rnb@example.com",
        RNB_REPLY_TO_ADDRESS="reply@example.com",
    )
    def test_build_monthly_leaderboard_email_no_new_users(self):
        """
        Input: leaderboard with one entry, no new usernames.
        Expected: HTML body does not contain "Bienvenue aux nouveaux inscrits".
        """
        leaderboard = [{"username": "alice", "edit_count": 5}]
        email = build_monthly_leaderboard_email(
            leaderboard, "février 2026", "recipient@example.com"
        )

        html_body = email.alternatives[0][0]
        self.assertNotIn("Bienvenue aux nouveaux inscrits", html_body)
