import itertools
from datetime import date, datetime
from zoneinfo import ZoneInfo

from batid.models import (
    KPI,
    Building,
    City,
    Department,
    Organization,
    SummerChallenge,
)
from batid.services.contribution_summary import (
    compute_contribution_summary,
    count_contributing,
)
from batid.services.kpi import (
    KPI_BUILDING_CHANGES_CONTRIBUTIONS,
    KPI_BUILDING_CHANGES_IMPORT_BAL,
    KPI_BUILDING_CHANGES_IMPORT_BDTOPO,
    KPI_CONTRIBUTING_CITIES_COUNT,
    KPI_CONTRIBUTING_ORGANIZATIONS_COUNT,
)
from batid.tests.factories.users import ContributorUserFactory, UserFactory
from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

PARIS = ZoneInfo("Europe/Paris")
# "now" used by the service tests: 15 October 2026, noon in Paris.
# The 30-day window starts on 15 September noon.
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=PARIS)
IN_WINDOW = datetime(2026, 10, 5, tzinfo=PARIS)
BEFORE_WINDOW = datetime(2026, 9, 1, tzinfo=PARIS)

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


def edition(user, created_at, city=None, department=None, origin=CONTRIBUTION):
    """
    Creates a building with Building.create_new, which records the event in the
    building history and writes its SummerChallenge row, then dates the row and
    sets its city and department (created_at is auto_now_add, the areas are
    resolved from shapes the tests don't have).
    """
    building = Building.create_new(
        user=user,
        event_origin=origin,
        status="constructed",
        addresses_cle_interop=[],
        shape=_square(),
        ext_ids=[],
    )
    SummerChallenge.objects.filter(event_id=building.event_id).update(
        created_at=created_at, city=city, department=department
    )
    return building


def member_of(user, organization):
    user.profile.organization = organization
    user.profile.save()
    return user


@override_settings(MAX_BUILDING_AREA=float("inf"))
class ContributionSummaryTest(TestCase):
    def setUp(self):
        self.gironde = Department.objects.create(code="33", name="Gironde")
        self.savoie = Department.objects.create(code="73", name="Savoie")
        self.talence = City.objects.create(code_insee="33522", name="Talence")
        self.merignac = City.objects.create(code_insee="33281", name="Mérignac")
        self.verrens = City.objects.create(code_insee="73311", name="Verrens-Arvey")
        self.mairie = Organization.objects.create(
            name="Commune de Talence", short_name="Talence"
        )
        self.rnb_team, _ = Organization.objects.get_or_create(
            name=settings.RNB_TEAM_ORG_NAME
        )
        self.alice = member_of(ContributorUserFactory(username="alice"), self.mairie)
        self.bob = ContributorUserFactory(username="bob")

    def test_empty(self):
        """
        Input: no contribution, no KPI.
        Expected: zeros and empty lists, no error; the totals are None until the
        nightly KPIs are computed.
        """
        data = compute_contribution_summary(now=NOW)

        self.assertEqual(data["cities"], {"total": None, "new": 0})
        self.assertEqual(data["organizations"], {"total": None, "new": 0})
        self.assertEqual(count_contributing(), {"cities": 0, "organizations": 0})
        self.assertEqual(data["building_changes"], {"total": 0, "contributions": 0})
        self.assertEqual(data["top"], {"users": [], "organizations": [], "cities": []})
        self.assertEqual(data["newcomers"], {"cities": [], "users": []})
        self.assertEqual(data["window_days"], 30)

    def test_rnb_team_counts_but_not_its_technical_account(self):
        """
        Input: in the window, a member of the RNB team organization contributes
        in Verrens-Arvey, a staff account and alice in Talence; the technical RNB
        account (which runs the imports) writes a row in Mérignac.
        Expected: the team member and the staff account are ranked like anyone;
        the technical account and Mérignac appear nowhere.
        """
        team_member = member_of(UserFactory(username="equipe"), self.rnb_team)
        staff = UserFactory(username="staff", is_staff=True)
        technical = member_of(UserFactory(username="RNB"), self.rnb_team)
        edition(team_member, IN_WINDOW, self.verrens, self.savoie)
        edition(staff, IN_WINDOW, self.talence, self.gironde)
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        edition(technical, IN_WINDOW, self.merignac, self.gironde, origin=IMPORT)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            sorted(u["username"] for u in data["top"]["users"]),
            ["alice", "equipe", "staff"],
        )
        self.assertEqual(
            sorted(o["name"] for o in data["top"]["organizations"]),
            ["Commune de Talence", settings.RNB_TEAM_ORG_NAME],
        )
        self.assertEqual(
            sorted(c["name"] for c in data["top"]["cities"]),
            ["Talence", "Verrens-Arvey"],
        )
        self.assertEqual(count_contributing(), {"cities": 2, "organizations": 2})

    def test_rankings_cover_the_last_30_days(self):
        """
        Input: bob contributes twice in Mérignac before the window (1 September),
        alice once in Talence in the window.
        Expected: rankings only show alice and Talence; the cumulative count of
        cities still includes Mérignac.
        """
        edition(self.bob, BEFORE_WINDOW, self.merignac, self.gironde)
        edition(self.bob, BEFORE_WINDOW, self.merignac, self.gironde)
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            data["top"]["users"],
            [{"username": "alice", "organization": "Talence", "count": 1}],
        )
        self.assertEqual(
            data["top"]["cities"],
            [
                {
                    "insee_code": "33522",
                    "name": "Talence",
                    "department": {"code": "33", "name": "Gironde"},
                    "count": 1,
                }
            ],
        )
        self.assertEqual(data["cities"]["new"], 1)
        self.assertEqual(count_contributing()["cities"], 2)

    def test_new_cities_are_those_first_contributed_in_the_window(self):
        """
        Input: Mérignac contributed before the window and again in it; Talence for
        the first time in the window; Verrens-Arvey touched by an import before
        the window (run as the technical RNB account, like every import), then
        contributed for the first time in it.
        Expected: new cities = Talence and Verrens-Arvey (an import is not a
        contribution), not Mérignac.
        """
        rnb_team_user = member_of(UserFactory(username="RNB"), self.rnb_team)
        edition(self.bob, BEFORE_WINDOW, self.merignac, self.gironde)
        edition(self.bob, IN_WINDOW, self.merignac, self.gironde)
        edition(self.alice, datetime(2026, 10, 1, tzinfo=PARIS), self.talence)
        edition(rnb_team_user, BEFORE_WINDOW, self.verrens, self.savoie, origin=IMPORT)
        edition(self.bob, datetime(2026, 10, 10, tzinfo=PARIS), self.verrens)

        data = compute_contribution_summary(now=NOW)

        # the latest first contribution first
        self.assertEqual(
            [c["name"] for c in data["newcomers"]["cities"]],
            ["Verrens-Arvey", "Talence"],
        )
        self.assertEqual(data["cities"]["new"], 2)

    def test_newcomers_include_first_time_contributors(self):
        """
        Input: bob contributed before the window and again in it; alice and carol
        (whose username is an email) contribute for the first time in it, carol
        last.
        Expected: newcomers users = carol (local part only), then alice; not bob.
        """
        carol = ContributorUserFactory(username="carol@mairie.fr")
        edition(self.bob, BEFORE_WINDOW, self.merignac, self.gironde)
        edition(self.bob, IN_WINDOW, self.merignac, self.gironde)
        edition(self.alice, datetime(2026, 10, 1, tzinfo=PARIS), self.talence)
        edition(carol, datetime(2026, 10, 10, tzinfo=PARIS), self.talence)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            data["newcomers"]["users"], [{"username": "carol"}, {"username": "alice"}]
        )

    def test_activity_of_the_window(self):
        """
        Input: in the window, alice makes 2 contributions in Talence, bob 1 in
        Mérignac (his first one, bob had none before); 3 contributions in the 30
        days before the window, by alice.
        Expected: 3 contributions in 2 cities by 2 contributors, 1 new
        contributor (bob), 3 contributions in the previous 30 days.
        """
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        edition(self.bob, IN_WINDOW, self.merignac, self.gironde)
        for _ in range(3):
            edition(self.alice, datetime(2026, 9, 1, tzinfo=PARIS), self.talence)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            data["activity"],
            {
                "contributions": 3,
                "cities": 2,
                "contributors": 2,
                "new_contributors": 1,
                "previous_contributions": 3,
            },
        )

    def test_7_day_window(self):
        """
        Input: alice contributes 10 days ago and 3 days ago, bob 3 days ago.
        Expected: with days=7, only the 2 contributions of 3 days ago are in the
        window; the one of 10 days ago is in the 7 days before.
        """
        edition(self.alice, datetime(2026, 10, 5, tzinfo=PARIS), self.talence)
        edition(self.alice, datetime(2026, 10, 12, tzinfo=PARIS), self.talence)
        edition(self.bob, datetime(2026, 10, 12, tzinfo=PARIS), self.merignac)

        data = compute_contribution_summary(now=NOW, days=7)

        self.assertEqual(data["window_days"], 7)
        self.assertEqual(data["activity"]["contributions"], 2)
        self.assertEqual(data["activity"]["previous_contributions"], 1)
        self.assertEqual(
            sorted(u["username"] for u in data["top"]["users"]), ["alice", "bob"]
        )

    def test_an_event_counts_once(self):
        """
        Input: one contribution writing 2 SummerChallenge rows (same event_id).
        Expected: 1 contribution in the rankings.
        """
        building = edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        row = SummerChallenge.objects.get(event_id=building.event_id)
        row.pk = None
        row.action = "set_address"
        row.save()

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(data["top"]["users"][0]["count"], 1)

    def test_organization_department_is_where_it_contributed_the_most(self):
        """
        Input: alice (Commune de Talence) contributes twice in Gironde and once
        in Savoie.
        Expected: the organization is shown with Gironde.
        """
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        edition(self.alice, IN_WINDOW, self.verrens, self.savoie)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            data["top"]["organizations"],
            [
                {
                    "name": "Commune de Talence",
                    "department": {"code": "33", "name": "Gironde"},
                    "count": 3,
                }
            ],
        )

    def test_email_usernames_are_not_published(self):
        """
        Input: a contributor whose username is an email address.
        Expected: only the part before the @ is returned.
        """
        edition(ContributorUserFactory(username="l.martin@mairie.fr"), IN_WINDOW)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(data["top"]["users"][0]["username"], "l.martin")

    def test_totals_are_the_latest_nightly_kpis(self):
        """
        Input: contributing cities and organizations KPIs on two days.
        Expected: the latest values.
        """
        for day, cities, organizations in [
            (date(2026, 10, 13), 1200, 80),
            (date(2026, 10, 14), 1248, 86),
        ]:
            KPI.objects.create(
                name=KPI_CONTRIBUTING_CITIES_COUNT, value_date=day, value=cities
            )
            KPI.objects.create(
                name=KPI_CONTRIBUTING_ORGANIZATIONS_COUNT,
                value_date=day,
                value=organizations,
            )

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(data["cities"]["total"], 1248)
        self.assertEqual(data["organizations"]["total"], 86)

    def test_building_changes_sum_the_last_30_complete_days(self):
        """
        Input: daily KPIs on 14 October (yesterday), 15 September (30 days ago)
        and 14 September (31 days ago), and today.
        Expected: only yesterday and 30 days ago are summed; contributions apart.
        """
        for day, bdtopo, bal, contributions in [
            (date(2026, 10, 14), 100, 10, 5),
            (date(2026, 9, 15), 50, 0, 2),
            (date(2026, 9, 14), 999, 999, 999),
            (date(2026, 10, 15), 999, 999, 999),
        ]:
            for name, value in [
                (KPI_BUILDING_CHANGES_IMPORT_BDTOPO, bdtopo),
                (KPI_BUILDING_CHANGES_IMPORT_BAL, bal),
                (KPI_BUILDING_CHANGES_CONTRIBUTIONS, contributions),
            ]:
                KPI.objects.create(name=name, value_date=day, value=value)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(data["building_changes"], {"total": 167, "contributions": 7})


@override_settings(MAX_BUILDING_AREA=float("inf"))
class ContributionSummaryApiTest(APITestCase):
    URL = "/api/alpha/contributions/summary/"

    def setUp(self):
        cache.clear()

    def test_returns_the_summary(self):
        """
        Input: 1 contribution made now.
        Expected: 200 with the contribution in the rankings.
        """
        edition(ContributorUserFactory(username="alice"), timezone.now())

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["top"]["users"][0]["username"], "alice")

    def test_days_selects_the_window(self):
        """
        Input: days=7, then days=30, then days=15.
        Expected: 200 with the matching window_days, then 400 for 15.
        """
        for days in [7, 30]:
            response = self.client.get(f"{self.URL}?days={days}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["window_days"], days)

        response = self.client.get(f"{self.URL}?days=15")

        self.assertEqual(response.status_code, 400)
        self.assertIn("days", response.json()["detail"])

    def test_response_is_cached(self):
        """
        Input: a first call, then a new contribution, then a second call.
        Expected: the second call returns the cached summary (no contributor yet).
        """
        self.client.get(self.URL)
        edition(ContributorUserFactory(), timezone.now())

        response = self.client.get(self.URL)

        self.assertEqual(response.json()["top"]["users"], [])
