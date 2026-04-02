import datetime
import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.core.mail import EmailMultiAlternatives
from django.test import override_settings
from django.test import TestCase
from freezegun import freeze_time

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
@freeze_time("2026-03-15")
class LeaderboardQueryTestCase(TestCase):
    def test_leaderboard_counts_distinct_events(self):
        """
        Input: frozen at 2026-03-15; user A creates 1 building then updates it (2 contribution events); user B creates 1 building (1 contribution event).
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

        results = get_monthly_edit_leaderboard(2026, 3)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["username"], "user_a")
        self.assertEqual(results[0]["edit_count"], 2)
        self.assertEqual(results[1]["username"], "user_b")
        self.assertEqual(results[1]["edit_count"], 1)

    def test_leaderboard_excludes_other_months(self):
        """
        Input: frozen at 2026-03-15; 1 building created in March 2026 with source=contribution.
        Expected: March 2026 query returns 1 result; April 2026 query returns 0.
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

        results = get_monthly_edit_leaderboard(2026, 3)
        self.assertEqual(len(results), 1)

        results_next = get_monthly_edit_leaderboard(2026, 4)
        self.assertEqual(len(results_next), 0)

    def test_leaderboard_excludes_non_contribution_source(self):
        """
        Input: frozen at 2026-03-15; 1 building created by a logged-in user with event_origin source != 'contribution'.
        Expected: leaderboard is empty (non-contribution edits are excluded).
        """
        user = ContributorUserFactory(
            username="user_import", email="import@example.com"
        )
        Building.create_new(
            user=user,
            event_origin={"source": "import"},
            status="constructed",
            addresses_id=[],
            shape=SIMPLE_POLYGON,
            ext_ids=[],
        )

        results = get_monthly_edit_leaderboard(2026, 3)
        self.assertEqual(len(results), 0)

    def test_leaderboard_excludes_null_event_user(self):
        """
        Input: frozen at 2026-03-15; 1 building created without a user (import source).
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

        results = get_monthly_edit_leaderboard(2026, 3)
        self.assertEqual(len(results), 0)

    def test_get_monthly_new_users(self):
        """
        Input: frozen at 2026-03-15; user A joined in March 2026 (default), user B's date_joined set to February 2026.
        Expected: March 2026 query returns user A only; February 2026 query returns user B only.
        """
        user_joined_this_month = User.objects.create_user(
            username="user_d", email="d@example.com"
        )
        user_last_month = User.objects.create_user(
            username="user_e", email="e@example.com"
        )

        last_month_date = datetime.datetime(2026, 2, 15, tzinfo=datetime.timezone.utc)
        User.objects.filter(pk=user_last_month.pk).update(date_joined=last_month_date)

        # check this month new user
        this_month_users = get_monthly_new_users(2026, 3)
        self.assertIn(user_joined_this_month, this_month_users)
        self.assertNotIn(user_last_month, this_month_users)

        # check last month new user
        last_month_users = get_monthly_new_users(2026, 2)
        self.assertNotIn(user_joined_this_month, last_month_users)
        self.assertIn(user_last_month, last_month_users)


@override_settings(
    MAX_BUILDING_AREA=float("inf"),
    RNB_SEND_ADDRESS="rnb@example.com",
    RNB_REPLY_TO_ADDRESS="reply@example.com",
)
@freeze_time("2026-03-15")
class LeaderboardEmailTestCase(TestCase):
    def setUp(self):
        # alice joined in February so she doesn't count as a new user in March
        self.alice = ContributorUserFactory(username="alice", email="alice@example.com")
        User.objects.filter(pk=self.alice.pk).update(
            date_joined=datetime.datetime(2026, 2, 1, tzinfo=datetime.timezone.utc)
        )
        # 1 create + 4 updates = 5 distinct contribution events for alice in March 2026
        b = Building.create_new(
            user=self.alice,
            event_origin={"source": "contribution"},
            status="constructed",
            addresses_id=[],
            shape=SIMPLE_POLYGON,
            ext_ids=[],
        )
        for status in ["demolished", "constructed", "demolished", "constructed"]:
            b.update(
                user=self.alice,
                event_origin={"source": "contribution"},
                status=status,
                addresses_id=None,
                shape=None,
            )

    def test_build_monthly_leaderboard_email_has_no_recipient(self):
        """
        Input: year=2026, month=3.
        Expected: returned EmailMultiAlternatives has to=[] (no recipient pre-set).
        """
        msg = build_monthly_leaderboard_email(2026, 3)

        self.assertEqual(msg.to, [])

    def test_build_monthly_leaderboard_email(self):
        """
        Input: year=2026, month=3; alice has 5 contribution edits, no new users in March.
        Expected: EmailMultiAlternatives with subject and HTML body containing month label,
        alice's username, and edit count 5.
        """
        msg = build_monthly_leaderboard_email(2026, 3)

        self.assertIsInstance(msg, EmailMultiAlternatives)
        self.assertIn("mars 2026", msg.subject)
        html_body = str(msg.alternatives[0][0])
        self.assertIn("alice", html_body)
        self.assertIn("5", html_body)
        self.assertIn("mars 2026", html_body)

    def test_build_monthly_leaderboard_email_with_new_users(self):
        """
        Input: year=2026, month=3; alice has 5 edits; bob and charlie joined in March 2026.
        Expected: HTML body contains "Bienvenue aux nouveaux inscrits" and both new usernames.
        """
        ContributorUserFactory(username="bob", email="bob@example.com")
        ContributorUserFactory(username="charlie", email="charlie@example.com")

        msg = build_monthly_leaderboard_email(2026, 3)

        html_body = str(msg.alternatives[0][0])
        self.assertIn("Bienvenue aux nouveaux inscrits", html_body)
        self.assertIn("bob", html_body)
        self.assertIn("charlie", html_body)

    def test_build_monthly_leaderboard_email_no_new_users(self):
        """
        Input: year=2026, month=3; alice has 5 edits, no users joined in March 2026.
        Expected: HTML body does not contain "Bienvenue aux nouveaux inscrits".
        """
        msg = build_monthly_leaderboard_email(2026, 3)

        html_body = str(msg.alternatives[0][0])
        self.assertNotIn("Bienvenue aux nouveaux inscrits", html_body)

