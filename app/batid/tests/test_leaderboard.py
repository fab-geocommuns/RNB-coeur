import datetime
import uuid

from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase
from django.test import override_settings

from batid.models.building import Building
from batid.services.email import build_monthly_leaderboard_email
from batid.services.leaderboard import get_monthly_edit_leaderboard
from batid.services.leaderboard import get_monthly_new_users


class LeaderboardQueryTestCase(TestCase):
    def _create_building(self, rnb_id, event_user, event_id):
        return Building.objects.create(
            rnb_id=rnb_id,
            event_user=event_user,
            event_id=event_id,
        )

    def test_leaderboard_counts_distinct_events(self):
        """
        Input: user A has 3 buildings via 2 distinct event_ids; user B has 1 building via 1 event_id.
        Expected: leaderboard has 2 entries, user A first with edit_count=2, user B second with edit_count=1.
        """
        user_a = User.objects.create_user(username="user_a", email="a@example.com")
        user_b = User.objects.create_user(username="user_b", email="b@example.com")
        event_a1 = uuid.uuid4()
        event_a2 = uuid.uuid4()
        event_b1 = uuid.uuid4()

        self._create_building("RNBA0000001", user_a, event_a1)
        self._create_building("RNBA0000002", user_a, event_a1)  # same event, counts as 1
        self._create_building("RNBA0000003", user_a, event_a2)
        self._create_building("RNBB0000001", user_b, event_b1)

        today = datetime.date.today()
        results = get_monthly_edit_leaderboard(today.year, today.month)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["event_user__username"], "user_a")
        self.assertEqual(results[0]["edit_count"], 2)
        self.assertEqual(results[1]["event_user__username"], "user_b")
        self.assertEqual(results[1]["edit_count"], 1)

    def test_leaderboard_excludes_other_months(self):
        """
        Input: 1 building created now (current month).
        Expected: current month query returns 1 result; next month query returns 0.
        """
        user = User.objects.create_user(username="user_c", email="c@example.com")
        self._create_building("RNBC0000001", user, uuid.uuid4())

        today = datetime.date.today()
        results = get_monthly_edit_leaderboard(today.year, today.month)
        self.assertEqual(len(results), 1)

        next_year = today.year if today.month < 12 else today.year + 1
        next_month = today.month + 1 if today.month < 12 else 1
        results_next = get_monthly_edit_leaderboard(next_year, next_month)
        self.assertEqual(len(results_next), 0)

    def test_leaderboard_excludes_null_event_user(self):
        """
        Input: 1 building with event_user=None.
        Expected: leaderboard is empty.
        """
        Building.objects.create(
            rnb_id="RNBD0000001", event_user=None, event_id=uuid.uuid4()
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
        Expected: EmailMultiAlternatives instance; subject and HTML body both contain the month label,
        username, and edit count.
        """
        leaderboard = [{"event_user__username": "alice", "edit_count": 5}]
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
