import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from batid.models import City, Department, EditionActivity, Organization
from batid.services.edition_stats import compute_edition_activity, period_bounds
from batid.tests.factories.users import ContributorUserFactory
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

PARIS = ZoneInfo("Europe/Paris")
# "now" used by the service tests: 15 October 2026, noon in Paris
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=PARIS)


def edition(user, edited_at, organization=None, city=None, department=None):
    return EditionActivity.objects.create(
        event_id=uuid.uuid4(),
        event_type="update",
        user=user,
        organization=organization,
        city=city,
        department=department,
        edited_at=edited_at,
    )


class PeriodBoundsTest(TestCase):
    def test_current_month_starts_at_midnight_paris_time(self):
        """
        Input: current_month, now = 15 October 2026.
        Expected: since = 1 October 2026 00:00 Paris time, no end.
        """
        since, until = period_bounds("current_month", NOW)

        self.assertEqual(since, datetime(2026, 10, 1, tzinfo=PARIS))
        self.assertIsNone(until)

    def test_last_month_in_january_is_december_of_previous_year(self):
        """
        Input: last_month, now = 10 January 2027.
        Expected: from 1 December 2026 (inclusive) to 1 January 2027 (exclusive), Paris time.
        """
        since, until = period_bounds("last_month", datetime(2027, 1, 10, tzinfo=PARIS))

        self.assertEqual(since, datetime(2026, 12, 1, tzinfo=PARIS))
        self.assertEqual(until, datetime(2027, 1, 1, tzinfo=PARIS))

    def test_month_boundary_uses_paris_time_not_utc(self):
        """
        Input: now = 1 November 2026 00:30 Paris time (still 31 October in UTC).
        Expected: current_month starts on 1 November.
        """
        now = datetime(2026, 11, 1, 0, 30, tzinfo=PARIS)

        since, _ = period_bounds("current_month", now)

        self.assertEqual(since, datetime(2026, 11, 1, tzinfo=PARIS))


class ComputeEditionActivityTest(TestCase):
    def setUp(self):
        self.alice = ContributorUserFactory(username="alice")
        self.bob = ContributorUserFactory(username="bob")
        self.mairie = Organization.objects.create(
            name="Mairie de Test", short_name="Mairie Test"
        )
        self.alice.profile.organization = self.mairie
        self.alice.profile.save()
        self.dpt = Department.objects.create(code="99", name="Département Test")
        self.city_a = City.objects.create(code_insee="99001", name="Ville A")
        self.city_b = City.objects.create(code_insee="99002", name="Ville B")

    def test_totals_and_rankings_of_the_current_month(self):
        """
        Input: in October, alice makes 2 editions in Ville A (with her organization)
        and bob 1 edition in Ville B; bob also made 1 edition in September.
        Expected: current_month counts 3 editions, 2 cities, 2 editors; alice ranks
        first among users, Ville A first among cities, the organization has 2 editions.
        """
        october = datetime(2026, 10, 5, tzinfo=PARIS)
        for _ in range(2):
            edition(self.alice, october, self.mairie, self.city_a, self.dpt)
        edition(self.bob, october, None, self.city_b, self.dpt)
        edition(self.bob, datetime(2026, 9, 20, tzinfo=PARIS), None, self.city_b)

        data = compute_edition_activity("current_month", now=NOW)

        self.assertEqual(
            data["period"],
            {"key": "current_month", "since": "2026-10-01", "until": None},
        )
        self.assertEqual(data["totals"], {"editions": 3, "cities": 2, "editors": 2})
        self.assertEqual(
            data["top"]["users"],
            [
                {
                    "rank": 1,
                    "username": "alice",
                    "organization_short_name": "Mairie Test",
                    "count": 2,
                },
                {
                    "rank": 2,
                    "username": "bob",
                    "organization_short_name": None,
                    "count": 1,
                },
            ],
        )
        self.assertEqual(
            data["top"]["organizations"],
            [
                {
                    "rank": 1,
                    "name": "Mairie de Test",
                    "short_name": "Mairie Test",
                    "count": 2,
                }
            ],
        )
        self.assertEqual(
            data["top"]["cities"][0],
            {
                "rank": 1,
                "insee_code": "99001",
                "name": "Ville A",
                "department": {"code": "99", "name": "Département Test"},
                "count": 2,
            },
        )
        self.assertEqual(
            data["top"]["departments"],
            [{"rank": 1, "code": "99", "name": "Département Test", "count": 3}],
        )

    def test_last_month_period(self):
        """
        Input: 1 edition on 30 September at 23:30 Paris time, 1 on 1 October.
        Expected: last_month (September) counts only the first one,
        with since/until = 2026-09-01 / 2026-09-30.
        """
        edition(self.alice, datetime(2026, 9, 30, 23, 30, tzinfo=PARIS))
        edition(self.alice, datetime(2026, 10, 1, 0, 10, tzinfo=PARIS))

        data = compute_edition_activity("last_month", now=NOW)

        self.assertEqual(data["totals"]["editions"], 1)
        self.assertEqual(data["period"]["since"], "2026-09-01")
        self.assertEqual(data["period"]["until"], "2026-09-30")

    def test_equal_counts_share_the_same_rank(self):
        """
        Input: alice, bob and carol make 1 edition each.
        Expected: all three users have rank 1.
        """
        carol = ContributorUserFactory(username="carol")
        for user in [self.alice, self.bob, carol]:
            edition(user, NOW)

        data = compute_edition_activity("current_month", now=NOW)

        self.assertEqual([u["rank"] for u in data["top"]["users"]], [1, 1, 1])

    def test_limit_applies_to_rankings(self):
        """
        Input: 3 users with 1 edition each, limit = 2.
        Expected: 2 users in the ranking, totals still count 3 editors.
        """
        carol = ContributorUserFactory(username="carol")
        for user in [self.alice, self.bob, carol]:
            edition(user, NOW)

        data = compute_edition_activity("current_month", limit=2, now=NOW)

        self.assertEqual(len(data["top"]["users"]), 2)
        self.assertEqual(data["totals"]["editors"], 3)

    def test_newcomers_are_those_whose_first_edition_is_in_the_period(self):
        """
        Input: alice edited Ville A in September and again in October;
        bob edits Ville B for the first time in October.
        Expected: current_month newcomers = bob, Ville B; the department, first edited
        in September, is not a newcomer.
        """
        edition(
            self.alice, datetime(2026, 9, 10, tzinfo=PARIS), None, self.city_a, self.dpt
        )
        edition(
            self.alice, datetime(2026, 10, 2, tzinfo=PARIS), None, self.city_a, self.dpt
        )
        edition(
            self.bob, datetime(2026, 10, 3, tzinfo=PARIS), None, self.city_b, self.dpt
        )

        newcomers = compute_edition_activity("current_month", now=NOW)["newcomers"]

        self.assertEqual([u["username"] for u in newcomers["users"]], ["bob"])
        self.assertEqual([c["name"] for c in newcomers["cities"]], ["Ville B"])
        self.assertEqual(newcomers["departments"], [])
        self.assertEqual(
            newcomers["users"][0]["first_edition_at"],
            datetime(2026, 10, 3, tzinfo=PARIS).isoformat(),
        )

    def test_period_all_has_no_newcomers(self):
        """
        Input: 1 edition, period = all.
        Expected: the edition is counted, newcomer lists are empty, since/until are None.
        """
        edition(self.alice, NOW)

        data = compute_edition_activity("all", now=NOW)

        self.assertEqual(data["totals"]["editions"], 1)
        self.assertEqual(data["period"], {"key": "all", "since": None, "until": None})
        self.assertEqual(
            data["newcomers"],
            {"users": [], "cities": [], "departments": [], "count": None},
        )
        self.assertIsNone(data["previous_period"])

    def test_newcomers_count_is_not_limited(self):
        """
        Input: 3 users make their first edition in October, limit = 2.
        Expected: 2 users listed, newcomers count = 3 users.
        """
        carol = ContributorUserFactory(username="carol")
        for user in [self.alice, self.bob, carol]:
            edition(user, NOW)

        newcomers = compute_edition_activity("current_month", limit=2, now=NOW)[
            "newcomers"
        ]

        self.assertEqual(len(newcomers["users"]), 2)
        self.assertEqual(newcomers["count"]["users"], 3)

    def test_current_month_is_compared_with_the_same_elapsed_time_last_month(self):
        """
        Input: now = 15 October noon; editions on 10 September and 20 September.
        Expected: previous_period covers 1–15 September noon and counts 1 edition.
        """
        edition(self.alice, datetime(2026, 9, 10, tzinfo=PARIS))
        edition(self.alice, datetime(2026, 9, 20, tzinfo=PARIS))

        previous = compute_edition_activity("current_month", now=NOW)["previous_period"]

        self.assertEqual(previous["since"], "2026-09-01")
        self.assertEqual(
            previous["until"], datetime(2026, 9, 15, 12, 0, tzinfo=PARIS).isoformat()
        )
        self.assertEqual(previous["editions"], 1)

    def test_last_month_is_compared_with_the_whole_month_before(self):
        """
        Input: now = 15 October; editions on 10 August and 20 August.
        Expected: last_month (September) is compared with all of August: 2 editions.
        """
        edition(self.alice, datetime(2026, 8, 10, tzinfo=PARIS))
        edition(self.alice, datetime(2026, 8, 20, tzinfo=PARIS))

        previous = compute_edition_activity("last_month", now=NOW)["previous_period"]

        self.assertEqual(previous["since"], "2026-08-01")
        self.assertEqual(previous["editions"], 2)

    def test_monthly_series_covers_the_last_12_months(self):
        """
        Input: now = 15 October 2026; 2 editions in October 2026, 1 in November 2025,
        1 in October 2025 (13 months ago).
        Expected: 12 months from 2025-11 to 2026-10, zeros filled,
        October 2025 not included.
        """
        edition(self.alice, datetime(2026, 10, 2, tzinfo=PARIS))
        edition(self.alice, datetime(2026, 10, 3, tzinfo=PARIS))
        edition(self.alice, datetime(2025, 11, 1, 0, 30, tzinfo=PARIS))
        edition(self.alice, datetime(2025, 10, 20, tzinfo=PARIS))

        monthly = compute_edition_activity("all", now=NOW)["monthly"]

        self.assertEqual(len(monthly), 12)
        self.assertEqual(monthly[0], {"month": "2025-11", "editions": 1})
        self.assertEqual(monthly[-1], {"month": "2026-10", "editions": 2})
        self.assertEqual(monthly[5], {"month": "2026-04", "editions": 0})


class EditionActivityApiTest(APITestCase):
    def setUp(self):
        cache.clear()

    def test_default_period_is_current_month(self):
        """
        Input: 1 edition made now, no query parameter.
        Expected: 200, period = current_month, 1 edition, the 3 available periods.
        """
        edition(ContributorUserFactory(), timezone.now())

        response = self.client.get("/api/alpha/editions/activity/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["period"]["key"], "current_month")
        self.assertEqual(data["totals"]["editions"], 1)
        self.assertEqual(
            data["available_periods"], ["current_month", "last_month", "all"]
        )

    def test_response_is_cached(self):
        """
        Input: a first call, then a new edition, then a second call.
        Expected: the second call returns the cached totals (0 editions).
        """
        self.client.get("/api/alpha/editions/activity/?period=all")
        edition(ContributorUserFactory(), timezone.now())

        response = self.client.get("/api/alpha/editions/activity/?period=all")

        self.assertEqual(response.json()["totals"]["editions"], 0)

    def test_invalid_period_returns_400(self):
        """
        Input: period = last_year.
        Expected: 400 mentioning the period parameter.
        """
        response = self.client.get("/api/alpha/editions/activity/?period=last_year")

        self.assertEqual(response.status_code, 400)
        self.assertIn("period", response.json()["detail"])

    def test_invalid_limit_returns_400(self):
        """
        Input: limit = 0, limit = 21, limit = abc.
        Expected: 400 for each of them.
        """
        for limit in ["0", "21", "abc"]:
            response = self.client.get(f"/api/alpha/editions/activity/?limit={limit}")
            self.assertEqual(response.status_code, 400, limit)
