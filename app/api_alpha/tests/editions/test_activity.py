import itertools
from datetime import datetime
from zoneinfo import ZoneInfo

from batid.models import (
    Address,
    Building,
    City,
    Department,
    Organization,
    SummerChallenge,
)
from batid.services.edition_stats import compute_edition_activity
from batid.tests.factories.users import ContributorUserFactory, UserFactory
from django.contrib.gis.geos import Polygon
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

PARIS = ZoneInfo("Europe/Paris")
# "now" used by the service tests: 15 October 2026, noon in Paris
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=PARIS)

CONTRIBUTION = {"source": "contribution", "contribution_id": 1}
IMPORT = {"source": "import", "id": 1}

# each building gets its own square, so that buildings never overlap
_square_index = itertools.count()


def _square() -> Polygon:
    x = 2.3 + next(_square_index) * 0.001
    y = 48.8
    size = 0.0002
    return Polygon(
        ((x, y), (x, y + size), (x + size, y + size), (x + size, y), (x, y)),
        srid=4326,
    )


def set_rows(event_id, created_at, city=None, department=None):
    """
    Dates the SummerChallenge rows of an event and sets their city and department
    (created_at is auto_now_add, the areas are resolved from shapes the tests don't have)
    """
    SummerChallenge.objects.filter(event_id=event_id).update(
        created_at=created_at, city=city, department=department
    )


def edition(
    user, created_at, city=None, department=None, origin=CONTRIBUTION, addresses=None
) -> Building:
    """
    Creates a building with Building.create_new, which records the event in the
    building history and writes its SummerChallenge rows (one "creation" row,
    plus one "set_address" row when addresses are given, sharing the same event_id).
    """
    building = Building.create_new(
        user=user,
        event_origin=origin,
        status="constructed",
        addresses_cle_interop=addresses or [],
        shape=_square(),
        ext_ids=[],
    )
    set_rows(building.event_id, created_at, city, department)
    return building


@override_settings(MAX_BUILDING_AREA=float("inf"))
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

    def test_totals_and_rankings_of_the_last_30_days(self):
        """
        Input: on 5 October, alice (member of an organization) makes 2 editions in
        Ville A and bob 1 edition in Ville B; bob also made 1 edition on 1 September,
        before the window.
        Expected: the last 30 days count 3 editions, 2 cities, 2 editors; alice ranks
        first among users, Ville A first among cities, the organization has 2 editions.
        """
        october = datetime(2026, 10, 5, tzinfo=PARIS)
        for _ in range(2):
            edition(self.alice, october, self.city_a, self.dpt)
        edition(self.bob, october, self.city_b, self.dpt)
        edition(self.bob, datetime(2026, 9, 1, tzinfo=PARIS), self.city_b)

        data = compute_edition_activity(days=30, now=NOW)

        self.assertEqual(data["period"], {"key": "last_30_days", "since": "2026-09-15"})
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

    def test_equal_counts_share_the_same_rank(self):
        """
        Input: alice and bob make 2 editions each, carol 1.
        Expected: dense rank: alice and bob have rank 1, carol rank 2 (not 3).
        """
        carol = ContributorUserFactory(username="carol")
        for user in [self.alice, self.alice, self.bob, self.bob, carol]:
            edition(user, NOW)

        data = compute_edition_activity(days=30, now=NOW)

        self.assertEqual(
            [(u["username"], u["rank"]) for u in data["top"]["users"]],
            [("alice", 1), ("bob", 1), ("carol", 2)],
        )

    def test_limit_applies_to_rankings(self):
        """
        Input: 3 users with 1 edition each, limit = 2.
        Expected: 2 users in the ranking, totals still count 3 editors.
        """
        carol = ContributorUserFactory(username="carol")
        for user in [self.alice, self.bob, carol]:
            edition(user, NOW)

        data = compute_edition_activity(days=30, limit=2, now=NOW)

        self.assertEqual(len(data["top"]["users"]), 2)
        self.assertEqual(data["totals"]["editors"], 3)

    def test_newcomers_are_those_whose_first_edition_is_in_the_period(self):
        """
        Input: alice edited Ville A in September and again in October;
        bob edits Ville B for the first time in October.
        Expected: newcomers of the last 30 days = bob, Ville B; the department, first
        edited on 10 September, is not a newcomer.
        """
        edition(self.alice, datetime(2026, 9, 10, tzinfo=PARIS), self.city_a, self.dpt)
        edition(self.alice, datetime(2026, 10, 2, tzinfo=PARIS), self.city_a, self.dpt)
        edition(self.bob, datetime(2026, 10, 3, tzinfo=PARIS), self.city_b, self.dpt)

        newcomers = compute_edition_activity(days=30, now=NOW)["newcomers"]

        self.assertEqual([u["username"] for u in newcomers["users"]], ["bob"])
        self.assertEqual([c["name"] for c in newcomers["cities"]], ["Ville B"])
        self.assertEqual(newcomers["departments"], [])
        self.assertEqual(
            newcomers["users"][0]["first_edition_at"],
            datetime(2026, 10, 3, tzinfo=PARIS).isoformat(),
        )

    def test_imports_do_not_make_newcomers_older(self):
        """
        Input: Ville B was touched by an import of the RNB team in September, then
        contributed by bob for the first time in October.
        Expected: Ville B and its department are newcomers of the last 30 days, their
        first contribution being bob's; the RNB team user is not a newcomer.
        """
        rnb_team = UserFactory(username="RNB")
        edition(
            rnb_team,
            datetime(2026, 9, 10, tzinfo=PARIS),
            self.city_b,
            self.dpt,
            origin=IMPORT,
        )
        edition(self.bob, datetime(2026, 10, 3, tzinfo=PARIS), self.city_b, self.dpt)

        newcomers = compute_edition_activity(days=30, now=NOW)["newcomers"]

        self.assertEqual([u["username"] for u in newcomers["users"]], ["bob"])
        self.assertEqual(
            newcomers["cities"],
            [
                {
                    "insee_code": "99002",
                    "name": "Ville B",
                    "department": {"code": "99", "name": "Département Test"},
                    "first_edition_at": datetime(2026, 10, 3, tzinfo=PARIS).isoformat(),
                }
            ],
        )
        self.assertEqual([d["code"] for d in newcomers["departments"]], ["99"])
        self.assertEqual(
            newcomers["count"], {"users": 1, "cities": 1, "departments": 1}
        )

    def test_city_rows_without_department_are_not_split(self):
        """
        Input: alice edits Ville A twice in October; the department of one of the
        rows could not be resolved (null).
        Expected: Ville A appears once in the ranking, with 2 contributions and its
        department.
        """
        edition(self.alice, NOW, self.city_a, self.dpt)
        edition(self.alice, NOW, self.city_a, None)

        cities = compute_edition_activity(days=30, now=NOW)["top"]["cities"]

        self.assertEqual(
            cities,
            [
                {
                    "rank": 1,
                    "insee_code": "99001",
                    "name": "Ville A",
                    "department": {"code": "99", "name": "Département Test"},
                    "count": 2,
                }
            ],
        )

    def test_whole_history_has_no_newcomers(self):
        """
        Input: 1 edition, days = None (whole history).
        Expected: the edition is counted, key all, newcomer lists are empty,
        newcomers count and previous_period are None.
        """
        edition(self.alice, NOW)

        data = compute_edition_activity(days=None, now=NOW)

        self.assertEqual(data["totals"]["editions"], 1)
        self.assertEqual(data["period"], {"key": "all", "since": None})
        self.assertEqual(
            data["newcomers"],
            {"users": [], "cities": [], "departments": [], "count": None},
        )
        self.assertIsNone(data["previous_period"])

    def test_newcomers_count_is_not_limited(self):
        """
        Input: 3 users make their first edition now, limit = 2.
        Expected: 2 users listed, newcomers count = 3 users.
        """
        carol = ContributorUserFactory(username="carol")
        for user in [self.alice, self.bob, carol]:
            edition(user, NOW)

        newcomers = compute_edition_activity(days=30, limit=2, now=NOW)["newcomers"]

        self.assertEqual(len(newcomers["users"]), 2)
        self.assertEqual(newcomers["count"]["users"], 3)

    def test_rolling_window_covers_the_last_n_days(self):
        """
        Input: now = 15 October noon, days = 30; editions on 15 September 13:00
        (inside the window), 15 September 11:00 (just before) and 20 August.
        Expected: key last_30_days, 1 edition; the previous 30 days
        (16 August noon – 15 September noon) count 2 editions.
        """
        edition(self.alice, datetime(2026, 9, 15, 13, 0, tzinfo=PARIS))
        edition(self.alice, datetime(2026, 9, 15, 11, 0, tzinfo=PARIS))
        edition(self.bob, datetime(2026, 8, 20, tzinfo=PARIS))

        data = compute_edition_activity(days=30, now=NOW)

        self.assertEqual(data["period"], {"key": "last_30_days", "since": "2026-09-15"})
        self.assertEqual(data["totals"]["editions"], 1)
        self.assertEqual(data["previous_period"]["since"], "2026-08-16")
        self.assertEqual(
            data["previous_period"]["until"],
            datetime(2026, 9, 15, 12, 0, tzinfo=PARIS).isoformat(),
        )
        self.assertEqual(data["previous_period"]["editions"], 2)

    def test_rolling_window_newcomers(self):
        """
        Input: now = 15 October, days = 7; alice edited in August and on 12 October,
        bob for the first time on 12 October.
        Expected: only bob is a newcomer of the last 7 days.
        """
        edition(self.alice, datetime(2026, 8, 10, tzinfo=PARIS))
        edition(self.alice, datetime(2026, 10, 12, tzinfo=PARIS))
        edition(self.bob, datetime(2026, 10, 12, tzinfo=PARIS))

        newcomers = compute_edition_activity(days=7, now=NOW)["newcomers"]

        self.assertEqual([u["username"] for u in newcomers["users"]], ["bob"])

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

        monthly = compute_edition_activity(days=None, now=NOW)["monthly"]

        self.assertEqual(len(monthly), 12)
        self.assertEqual(monthly[0], {"month": "2025-11", "editions": 1})
        self.assertEqual(monthly[-1], {"month": "2026-10", "editions": 2})
        self.assertEqual(monthly[5], {"month": "2026-04", "editions": 0})

    def test_month_boundary_of_editions_uses_paris_time(self):
        """
        Input: 1 edition on 1 October 2026 at 00:30 Paris time (30 September 22:30 UTC).
        Expected: it belongs to the "2026-10" month of the series, not to "2026-09".
        """
        edition(self.alice, datetime(2026, 10, 1, 0, 30, tzinfo=PARIS))

        monthly = compute_edition_activity(now=NOW)["monthly"]

        self.assertEqual(monthly[-1], {"month": "2026-10", "editions": 1})
        self.assertEqual(monthly[-2], {"month": "2026-09", "editions": 0})


@override_settings(MAX_BUILDING_AREA=float("inf"))
class ContributionFilterTest(TestCase):
    """What is counted as a contribution, out of the SummerChallenge rows"""

    def setUp(self):
        self.rnb_team = UserFactory(username="RNB")
        self.alice = ContributorUserFactory(username="alice")

    def test_rnb_team_imports_are_excluded_but_its_contributions_count(self):
        """
        Input: the RNB team user makes an import (origin "import") and a manual
        contribution (origin "contribution") now; both write SummerChallenge rows.
        Expected: only the contribution is counted; the RNB team user is ranked
        with 1 contribution.
        """
        edition(self.rnb_team, NOW, origin=IMPORT)
        edition(self.rnb_team, NOW)

        data = compute_edition_activity(days=30, now=NOW)

        self.assertEqual(SummerChallenge.objects.count(), 2)
        self.assertEqual(data["totals"]["editions"], 1)
        self.assertEqual(
            [(u["username"], u["count"]) for u in data["top"]["users"]], [("RNB", 1)]
        )

    def test_staff_contributions_count(self):
        """
        Input: a staff user makes 1 contribution.
        Expected: it is counted as any other contribution.
        """
        staff = UserFactory(username="staff", is_staff=True)
        edition(staff, NOW)

        data = compute_edition_activity(days=30, now=NOW)

        self.assertEqual(data["totals"], {"editions": 1, "cities": 0, "editors": 1})

    def test_rows_of_the_same_event_count_as_one_contribution(self):
        """
        Input: alice creates a building with an address: one event writing 2
        SummerChallenge rows ("creation" and "set_address") with the same event_id.
        Expected: 1 contribution in the totals, the user ranking, the monthly series
        and the previous_period of a window 36 days later.
        """
        Address.objects.create(cle_interop="addr1")
        edition(self.alice, NOW, addresses=["addr1"])

        data = compute_edition_activity(days=30, now=NOW)
        next_month = compute_edition_activity(
            days=30, now=datetime(2026, 11, 20, tzinfo=PARIS)
        )

        self.assertEqual(SummerChallenge.objects.count(), 2)
        self.assertEqual(data["totals"]["editions"], 1)
        self.assertEqual(data["top"]["users"][0]["count"], 1)
        self.assertEqual(data["monthly"][-1]["editions"], 1)
        self.assertEqual(next_month["previous_period"]["editions"], 1)

    def test_events_moved_to_the_history_table_are_counted(self):
        """
        Input: alice creates a building, then updates its status: the creation event
        now only exists in batid_building_history.
        Expected: both events are counted (2 contributions).
        """
        building = edition(self.alice, NOW)
        building.update(
            user=self.alice,
            event_origin=CONTRIBUTION,
            status="demolished",
            addresses_cle_interop=None,
        )
        set_rows(building.event_id, NOW)

        data = compute_edition_activity(days=30, now=NOW)

        self.assertEqual(data["totals"]["editions"], 2)


@override_settings(MAX_BUILDING_AREA=float("inf"))
class EditionActivityApiTest(APITestCase):
    def setUp(self):
        cache.clear()

    def test_default_period_is_the_last_30_days(self):
        """
        Input: 1 edition made now, no query parameter.
        Expected: 200, period key last_30_days, 1 edition.
        """
        edition(ContributorUserFactory(), timezone.now())

        response = self.client.get("/api/alpha/editions/activity/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["period"]["key"], "last_30_days")
        self.assertEqual(data["totals"]["editions"], 1)

    def test_response_is_cached(self):
        """
        Input: a first call, then a new edition, then a second call.
        Expected: the second call returns the cached totals (0 editions).
        """
        self.client.get("/api/alpha/editions/activity/?period=all")
        edition(ContributorUserFactory(), timezone.now())

        response = self.client.get("/api/alpha/editions/activity/?period=all")

        self.assertEqual(response.json()["totals"]["editions"], 0)

    def test_period_all_returns_the_whole_history(self):
        """
        Input: 1 edition made 2 years ago, period = all.
        Expected: 200, period key all, 1 edition.
        """
        edition(ContributorUserFactory(), datetime(2024, 10, 1, tzinfo=PARIS))

        response = self.client.get("/api/alpha/editions/activity/?period=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["period"]["key"], "all")
        self.assertEqual(response.json()["totals"]["editions"], 1)

    def test_calendar_periods_return_400(self):
        """
        Input: period = current_month, period = last_month.
        Expected: 400 mentioning the period parameter: only all is accepted.
        """
        for period in ["current_month", "last_month"]:
            response = self.client.get(f"/api/alpha/editions/activity/?period={period}")
            self.assertEqual(response.status_code, 400, period)
            self.assertIn("period", response.json()["detail"])

    def test_days_returns_a_rolling_window(self):
        """
        Input: 1 edition made now, days = 30.
        Expected: 200, period key last_30_days, 1 edition.
        """
        edition(ContributorUserFactory(), timezone.now())

        response = self.client.get("/api/alpha/editions/activity/?days=30")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["period"]["key"], "last_30_days")
        self.assertEqual(response.json()["totals"]["editions"], 1)

    def test_invalid_days_returns_400(self):
        """
        Input: days = 0, days = 366, days = abc.
        Expected: 400 mentioning the days parameter for each of them.
        """
        for days in ["0", "366", "abc"]:
            response = self.client.get(f"/api/alpha/editions/activity/?days={days}")
            self.assertEqual(response.status_code, 400, days)
            self.assertIn("days", response.json()["detail"])

    def test_days_and_period_cannot_be_combined(self):
        """
        Input: days = 30 and period = all.
        Expected: 400.
        """
        response = self.client.get("/api/alpha/editions/activity/?days=30&period=all")

        self.assertEqual(response.status_code, 400)

    def test_invalid_limit_returns_400(self):
        """
        Input: limit = 0, limit = 21, limit = abc.
        Expected: 400 for each of them.
        """
        for limit in ["0", "21", "abc"]:
            response = self.client.get(f"/api/alpha/editions/activity/?limit={limit}")
            self.assertEqual(response.status_code, 400, limit)
