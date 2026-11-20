import itertools
import json
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import sentry_sdk
from batid.models import (
    KPI,
    Building,
    City,
    Department,
    Organization,
    SummerChallenge,
)
from batid.services import contribution_summary
from batid.services.contribution_summary import (
    CACHE_KEY,
    PERIOD_KEYS,
    compute_all_summaries,
    compute_contribution_summary,
    summaries_cache_key,
)
from batid.services.kpi import (
    KPI_BUILDING_CHANGES_CONTRIBUTIONS,
    KPI_BUILDING_CHANGES_IMPORT_BAL,
    KPI_BUILDING_CHANGES_IMPORT_BDTOPO,
)
from batid.tests.factories.users import ContributorUserFactory, UserFactory
from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.core.cache import cache
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.transport import Transport

PARIS = ZoneInfo("Europe/Paris")
# "now" used by the service tests: 15 October 2026, noon in Paris.
# The 30-day window starts on 15 September noon.
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=PARIS)
SUMMARIES_CACHE_KEY = summaries_cache_key()
SUMMARIES_URL = "/api/alpha/contributions/summaries/"
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
        Expected: zeros and empty lists, no error.
        """
        data = compute_contribution_summary(now=NOW)

        self.assertEqual(data["cities"], {"total": 0, "new": 0})
        self.assertEqual(data["organizations"], {"total": 0, "new": 0})
        self.assertEqual(data["building_changes"], {"total": 0, "contributions": 0})
        self.assertEqual(data["top"], {"users": [], "organizations": [], "cities": []})
        self.assertEqual(data["newcomers"], {"users": []})
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
            sorted(["Commune de Talence", settings.RNB_TEAM_ORG_NAME]),
        )
        self.assertEqual(
            sorted(c["name"] for c in data["top"]["cities"]),
            ["Talence", "Verrens-Arvey"],
        )
        self.assertEqual(data["cities"], {"total": 2, "new": 2})
        self.assertEqual(data["organizations"], {"total": 2, "new": 2})

    def test_rankings_cover_the_last_30_days(self):
        """
        Input: bob contributes twice in Mérignac before the window (1 September),
        alice once in Talence in the window.
        Expected: rankings and counts only show alice and Talence.
        """
        edition(self.bob, BEFORE_WINDOW, self.merignac, self.gironde)
        edition(self.bob, BEFORE_WINDOW, self.merignac, self.gironde)
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            data["top"]["users"],
            [
                {
                    "username": "alice",
                    "organization": "Commune de Talence",
                    "organization_short_name": "Talence",
                    "count": 1,
                }
            ],
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
        self.assertEqual(data["cities"], {"total": 1, "new": 1})

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

    def test_7_day_window(self):
        """
        Input: alice contributes 10 days ago and 3 days ago, bob 3 days ago.
        Expected: with days=7, only the contributions of 3 days ago are ranked:
        alice and bob have 1 each.
        """
        edition(self.alice, datetime(2026, 10, 5, tzinfo=PARIS), self.talence)
        edition(self.alice, datetime(2026, 10, 12, tzinfo=PARIS), self.talence)
        edition(self.bob, datetime(2026, 10, 12, tzinfo=PARIS), self.merignac)

        data = compute_contribution_summary(now=NOW, days=7)

        self.assertEqual(data["window_days"], 7)
        self.assertEqual(
            sorted((u["username"], u["count"]) for u in data["top"]["users"]),
            [("alice", 1), ("bob", 1)],
        )

    def test_whole_period_starts_at_the_edition_opening(self):
        """
        Input: bob contributes in Verrens-Arvey during the 2024 summer game,
        alice in Talence in June 2025, bob in Mérignac in the window.
        Expected: with days=None, the period starts on 1 April 2025: alice and
        bob are ranked with 1 contribution each, Talence and Mérignac are the
        cities of the period, both new; alice is the only newcomer, bob
        contributed before.
        """
        edition(self.bob, datetime(2024, 7, 1, tzinfo=PARIS), self.verrens)
        edition(self.alice, datetime(2025, 6, 1, tzinfo=PARIS), self.talence)
        edition(self.bob, IN_WINDOW, self.merignac)

        data = compute_contribution_summary(now=NOW, days=None)

        self.assertIsNone(data["window_days"])
        self.assertEqual(data["since"], "2025-04-01T00:00:00+02:00")
        self.assertEqual(
            sorted((u["username"], u["count"]) for u in data["top"]["users"]),
            [("alice", 1), ("bob", 1)],
        )
        self.assertEqual(
            sorted(c["name"] for c in data["top"]["cities"]),
            ["Mérignac", "Talence"],
        )
        self.assertEqual(data["cities"], {"total": 2, "new": 2})
        self.assertEqual(data["newcomers"]["users"], [{"username": "alice"}])

    def test_periods_computed_together_are_nested(self):
        """
        Input: alice (Talence's town hall) in Talence 3 days ago, bob (no
        organization) in Mérignac 2 weeks ago, alice in Mérignac in May 2025,
        carol (RNB team) in Verrens-Arvey in June 2025, bob in Talence during
        the 2024 summer game; the 3 periods computed together.
        Expected: each shorter period is included in the longer one, for the
        totals and the first-time counts of cities and organizations, with the
        exact figures below and the same updated_at.
        """
        carol = member_of(ContributorUserFactory(username="carol"), self.rnb_team)
        edition(self.alice, datetime(2026, 10, 12, tzinfo=PARIS), self.talence)
        edition(self.bob, datetime(2026, 10, 1, tzinfo=PARIS), self.merignac)
        edition(self.alice, datetime(2025, 5, 1, tzinfo=PARIS), self.merignac)
        edition(carol, datetime(2025, 6, 1, tzinfo=PARIS), self.verrens)
        edition(self.bob, datetime(2024, 7, 1, tzinfo=PARIS), self.talence)

        data = compute_all_summaries(now=NOW)

        self.assertEqual(
            {key: data[key]["cities"] for key in PERIOD_KEYS},
            {
                "7": {"total": 1, "new": 0},
                "30": {"total": 2, "new": 0},
                "all": {"total": 3, "new": 2},
            },
        )
        self.assertEqual(
            {key: data[key]["organizations"] for key in PERIOD_KEYS},
            {
                "7": {"total": 1, "new": 0},
                "30": {"total": 1, "new": 0},
                "all": {"total": 2, "new": 2},
            },
        )
        self.assertEqual(len({data[key]["updated_at"] for key in PERIOD_KEYS}), 1)

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
        # created_at is set on save: put the row back in the window
        SummerChallenge.objects.filter(pk=row.pk).update(created_at=IN_WINDOW)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(data["top"]["users"][0]["count"], 1)

    def test_organizations_have_no_department(self):
        """
        Input: alice (Commune de Talence) contributes twice in Gironde and once
        in Savoie.
        Expected: the organization is ranked with its name and short name,
        without department.
        """
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        edition(self.alice, IN_WINDOW, self.verrens, self.savoie)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            data["top"]["organizations"],
            [{"name": "Commune de Talence", "short_name": "Talence", "count": 3}],
        )

    def test_data_fix_updates_are_not_contributions(self):
        """
        Input: alice creates a building; a data fix (eg. the replacement of
        obsolete BAN addresses) run by paul updates it, then alice updates it
        as a contribution.
        Expected: paul writes no SummerChallenge row and is neither ranked nor
        a newcomer; alice's update is still scored.
        """
        paul = UserFactory(username="paul")
        building = edition(self.alice, IN_WINDOW, self.talence, self.gironde)
        building.update(
            user=paul,
            event_origin={"source": "data_fix", "id": 1},
            status="demolished",
            addresses_cle_interop=None,
        )
        building.update(
            user=self.alice,
            event_origin=CONTRIBUTION,
            status="constructed",
            addresses_cle_interop=None,
        )

        self.assertFalse(SummerChallenge.objects.filter(user=paul).exists())
        self.assertTrue(
            SummerChallenge.objects.filter(
                user=self.alice, action="update_status"
            ).exists()
        )
        data = compute_contribution_summary()
        self.assertEqual([u["username"] for u in data["top"]["users"]], ["alice"])
        self.assertNotIn("paul", [u["username"] for u in data["newcomers"]["users"]])

    def test_organization_has_its_name_and_short_name_in_every_ranking(self):
        """
        Input: alice, member of "Commune de Talence" (short name "Talence"),
        contributes in the window.
        Expected: both the name and the short name are returned, next to alice
        and in the organizations ranking.
        """
        edition(self.alice, IN_WINDOW, self.talence, self.gironde)

        data = compute_contribution_summary(now=NOW)

        user = data["top"]["users"][0]
        self.assertEqual(user["organization"], "Commune de Talence")
        self.assertEqual(user["organization_short_name"], "Talence")
        organization = data["top"]["organizations"][0]
        self.assertEqual(organization["name"], "Commune de Talence")
        self.assertEqual(organization["short_name"], "Talence")

    def test_organization_without_short_name(self):
        """
        Input: carole, member of an organization whose short name is empty
        (""), contributes in the window.
        Expected: its short name is null, next to carole and in the
        organizations ranking; its name is returned as is.
        """
        departement = Organization.objects.create(
            name="Département de la Gironde", short_name=""
        )
        carole = member_of(ContributorUserFactory(username="carole"), departement)
        edition(carole, IN_WINDOW, self.talence, self.gironde)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            data["top"]["users"],
            [
                {
                    "username": "carole",
                    "organization": "Département de la Gironde",
                    "organization_short_name": None,
                    "count": 1,
                }
            ],
        )
        self.assertEqual(
            data["top"]["organizations"],
            [{"name": "Département de la Gironde", "short_name": None, "count": 1}],
        )

    def test_user_without_organization(self):
        """
        Input: bob, member of no organization, contributes in the window.
        Expected: their organization and its short name are both null.
        """
        edition(self.bob, IN_WINDOW, self.talence, self.gironde)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(
            data["top"]["users"],
            [
                {
                    "username": "bob",
                    "organization": None,
                    "organization_short_name": None,
                    "count": 1,
                }
            ],
        )
        self.assertEqual(data["top"]["organizations"], [])

    def test_email_usernames_are_not_published(self):
        """
        Input: a contributor whose username is an email address.
        Expected: only the part before the @ is returned.
        """
        edition(ContributorUserFactory(username="l.martin@mairie.fr"), IN_WINDOW)

        data = compute_contribution_summary(now=NOW)

        self.assertEqual(data["top"]["users"][0]["username"], "l.martin")

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

    def test_building_changes_end_on_the_latest_computed_day(self):
        """
        Input: at 2 am in Paris on 15 October, the KPIs of 14 October are not
        computed yet (the cron runs at 3 am UTC); KPIs on 13 October and on
        14 and 13 September.
        Expected: the 30 days end on 13 October: 13 October and 14 September
        are summed, 13 September is not.
        """
        for day, value in [
            (date(2026, 10, 13), 10),
            (date(2026, 9, 14), 5),
            (date(2026, 9, 13), 999),
        ]:
            KPI.objects.create(
                name=KPI_BUILDING_CHANGES_CONTRIBUTIONS, value_date=day, value=value
            )

        data = compute_contribution_summary(
            now=datetime(2026, 10, 15, 2, 0, tzinfo=PARIS)
        )

        self.assertEqual(data["building_changes"], {"total": 15, "contributions": 15})

    def test_building_changes_of_the_whole_period(self):
        """
        Input: daily KPIs on 31 March 2025, 1 April 2025 and 14 October 2026
        (yesterday).
        Expected: with days=None, the KPIs from 1 April 2025 are summed.
        """
        for day, value in [
            (date(2025, 3, 31), 999),
            (date(2025, 4, 1), 10),
            (date(2026, 10, 14), 5),
        ]:
            KPI.objects.create(
                name=KPI_BUILDING_CHANGES_CONTRIBUTIONS, value_date=day, value=value
            )

        data = compute_contribution_summary(now=NOW, days=None)

        self.assertEqual(data["building_changes"], {"total": 15, "contributions": 15})


# a cache of its own, so that the tests never touch the Redis one
@override_settings(
    MAX_BUILDING_AREA=float("inf"),
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
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
        Input: days=7, days=30, days=all, then days=15.
        Expected: 200 with the matching window_days (null for all), then 400
        for 15.
        """
        for days, window_days in [("7", 7), ("30", 30), ("all", None)]:
            response = self.client.get(f"{self.URL}?days={days}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["window_days"], window_days)

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

    def test_outdated_summary_is_served_while_another_request_refreshes_it(self):
        """
        Input: an outdated cached summary, and the refresh lock already taken
        by another request.
        Expected: the outdated summary is returned, without computing.
        """
        stale = {"window_days": 30, "stale": True}
        cache.set(
            SUMMARIES_CACHE_KEY,
            {"data": {"30": stale}, "fresh_until": time.time() - 1},
            60,
        )
        cache.add(f"{SUMMARIES_CACHE_KEY}:refreshing", True, 60)

        with patch.object(contribution_summary, "compute_all_summaries") as compute:
            response = self.client.get(self.URL)

        self.assertEqual(response.json(), stale)
        compute.assert_not_called()

    def test_outdated_summary_is_recomputed(self):
        """
        Input: an outdated cached summary, nobody refreshing it, then a
        contribution.
        Expected: the summary is recomputed and the lock released.
        """
        cache.set(
            SUMMARIES_CACHE_KEY,
            {"data": {"30": {"stale": True}}, "fresh_until": time.time() - 1},
            60,
        )
        edition(ContributorUserFactory(username="alice"), timezone.now())

        response = self.client.get(self.URL)

        self.assertEqual(response.json()["top"]["users"][0]["username"], "alice")
        self.assertIsNone(cache.get(f"{SUMMARIES_CACHE_KEY}:refreshing"))

    def test_periods_are_computed_together(self):
        """
        Input: a call with days=7, then with days=30 and days=all.
        Expected: the first call computes the 3 periods, the next ones compute
        nothing.
        """
        with patch.object(
            contribution_summary,
            "compute_contribution_summary",
            wraps=contribution_summary.compute_contribution_summary,
        ) as compute:
            self.client.get(f"{self.URL}?days=7")
            self.assertEqual(compute.call_count, 3)

            for days in ["30", "all"]:
                self.client.get(f"{self.URL}?days={days}")

        self.assertEqual(compute.call_count, 3)

    def test_shorter_period_never_counts_more_cities(self):
        """
        Input: a call with days=30, then a contribution in a new city, then a
        call with days=7.
        Expected: the 7-day period counts no more cities than the 30-day one
        (it is not computed later, with the new city).
        """
        response_30 = self.client.get(f"{self.URL}?days=30").json()
        city = City.objects.create(code_insee="33063", name="Bordeaux")
        edition(ContributorUserFactory(), timezone.now(), city=city)

        response_7 = self.client.get(f"{self.URL}?days=7").json()

        self.assertEqual(response_7["cities"], response_30["cities"])
        self.assertEqual(response_7["updated_at"], response_30["updated_at"])

    def test_empty_cache_waits_for_the_request_computing_it(self):
        """
        Input: an empty cache, the lock held by another request, which stores
        the summary while this one waits.
        Expected: the stored summary is returned, without computing.
        """
        lock_key = f"{SUMMARIES_CACHE_KEY}:refreshing"
        cache.add(lock_key, True, 60)
        computed = {"30": {"window_days": 30, "computed_elsewhere": True}}

        def other_request_stores_it(_seconds):
            cache.set(
                SUMMARIES_CACHE_KEY,
                {"data": computed, "fresh_until": time.time() + 60},
                60,
            )

        with patch.object(
            contribution_summary.time, "sleep", side_effect=other_request_stores_it
        ), patch.object(contribution_summary, "compute_all_summaries") as compute:
            response = self.client.get(self.URL)

        self.assertEqual(response.json(), computed["30"])
        compute.assert_not_called()
        # the lock is still the other request's
        self.assertTrue(cache.get(lock_key))

    def test_empty_cache_is_computed_when_the_other_request_failed(self):
        """
        Input: an empty cache, the lock held by another request, which fails
        (releases the lock without storing anything) while this one waits.
        Expected: this request takes the lock, computes the summary and
        releases the lock.
        """
        lock_key = f"{SUMMARIES_CACHE_KEY}:refreshing"
        cache.add(lock_key, True, 60)
        edition(ContributorUserFactory(username="alice"), timezone.now())

        with patch.object(
            contribution_summary.time,
            "sleep",
            side_effect=lambda _seconds: cache.delete(lock_key),
        ):
            response = self.client.get(self.URL)

        self.assertEqual(response.json()["top"]["users"][0]["username"], "alice")
        self.assertIsNone(cache.get(lock_key))

    def test_empty_cache_is_computed_after_the_wait(self):
        """
        Input: an empty cache, the lock held by another request during the
        whole wait (shortened to nothing).
        Expected: this request computes the summary anyway and leaves the
        other request's lock.
        """
        lock_key = f"{SUMMARIES_CACHE_KEY}:refreshing"
        cache.add(lock_key, True, 60)
        edition(ContributorUserFactory(username="alice"), timezone.now())

        with patch.object(contribution_summary, "EMPTY_CACHE_WAIT_SECONDS", 0):
            response = self.client.get(self.URL)

        self.assertEqual(response.json()["top"]["users"][0]["username"], "alice")
        self.assertTrue(cache.get(lock_key))

    def test_outdated_summary_is_served_when_the_refresh_fails(self):
        """
        Input: an outdated cached summary, and a refresh that raises a
        database error.
        Expected: 200 with the outdated summary, the error logged and the lock
        released.
        """
        stale = {"window_days": 30, "stale": True}
        cache.set(
            SUMMARIES_CACHE_KEY,
            {"data": {"30": stale}, "fresh_until": time.time() - 1},
            60,
        )

        with patch.object(
            contribution_summary,
            "compute_all_summaries",
            side_effect=DatabaseError("connection lost"),
        ), self.assertLogs(contribution_summary.logger, level="ERROR"):
            response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), stale)
        self.assertIsNone(cache.get(f"{SUMMARIES_CACHE_KEY}:refreshing"))

    def test_summary_stored_just_before_the_lock_is_not_recomputed(self):
        """
        Input: an empty cache when read; another request stores the summary
        and releases the lock just before this one takes the lock.
        Expected: the stored summary is returned, without computing, and the
        lock released.
        """
        lock_key = f"{SUMMARIES_CACHE_KEY}:refreshing"
        stored = {"30": {"window_days": 30, "computed_elsewhere": True}}
        real_add = cache.add

        def other_request_finishes_first(key, *args, **kwargs):
            if key == lock_key:
                cache.set(
                    SUMMARIES_CACHE_KEY,
                    {"data": stored, "fresh_until": time.time() + 60},
                    60,
                )
            return real_add(key, *args, **kwargs)

        with patch.object(
            cache, "add", side_effect=other_request_finishes_first
        ), patch.object(
            contribution_summary,
            "compute_all_summaries",
            return_value={"30": {"recomputed": True}},
        ) as compute:
            response = self.client.get(self.URL)

        self.assertEqual(response.json(), stored["30"])
        compute.assert_not_called()
        self.assertIsNone(cache.get(lock_key))

    def test_failure_with_an_empty_cache_is_raised(self):
        """
        Input: an empty cache, and a computation that raises a database error.
        Expected: the error is raised (nothing to serve instead) and the lock
        released.
        """
        with patch.object(
            contribution_summary,
            "compute_all_summaries",
            side_effect=DatabaseError("connection lost"),
        ), self.assertRaises(DatabaseError):
            contribution_summary.get_contribution_summary(30)

        self.assertIsNone(cache.get(f"{SUMMARIES_CACHE_KEY}:refreshing"))

    def test_each_period_is_the_summary_computed_before(self):
        """
        Input: a contribution, then a call for each period, the clock frozen.
        Expected: no format or figure change: each response is exactly what
        compute_contribution_summary returns for that instant and period.
        """
        edition(ContributorUserFactory(username="alice"), timezone.now())
        frozen = timezone.now()

        with patch.object(contribution_summary.timezone, "now", return_value=frozen):
            for days, window_days in [("7", 7), ("30", 30), ("all", None)]:
                response = self.client.get(f"{self.URL}?days={days}")
                expected = compute_contribution_summary(now=frozen, days=window_days)
                self.assertEqual(response.json(), json.loads(json.dumps(expected)))

    def test_entries_of_the_previous_code_are_left_alone(self):
        """
        Input: fresh entries and held refresh locks under the keys of the
        previous code (one per period), as during a deploy, when both codes
        share the cache.
        Expected: the new code neither reads them (it computes its summary,
        not blocked by their locks) nor changes them (the previous code still
        reads its own).
        """
        old = {"data": {"from_previous_code": True}, "fresh_until": time.time() + 600}
        old_entries = {f"{CACHE_KEY}:{key}": old for key in PERIOD_KEYS}
        old_entries.update(
            {f"{CACHE_KEY}:{key}:refreshing": True for key in PERIOD_KEYS}
        )
        cache.set_many(old_entries, 600)

        response = self.client.get(f"{self.URL}?days=30")

        self.assertEqual(response.json()["window_days"], 30)
        self.assertEqual(cache.get_many(list(old_entries)), old_entries)

    def test_entry_in_the_previous_format_is_not_read(self):
        """
        Input: a fresh entry under the key of the previous format (organizations
        under a single merged label), as cached before the deploy.
        Expected: the summary is computed again instead of the entry being
        served; the entry is left alone.
        """
        old_key = f"{CACHE_KEY}:{','.join(PERIOD_KEYS)}"
        old = {
            "data": {key: {"from_previous_format": True} for key in PERIOD_KEYS},
            "fresh_until": time.time() + 600,
        }
        cache.set(old_key, old, 600)

        response = self.client.get(f"{self.URL}?days=30")

        self.assertEqual(response.json()["window_days"], 30)
        self.assertEqual(cache.get(old_key), old)

    def test_entry_without_a_new_period_is_not_read(self):
        """
        Input: a fresh entry holding the 7, 30 and all periods, then a 90-day
        period added to the periods served.
        Expected: the 90-day summary is computed (the entry is under another
        key), instead of a KeyError on the entry missing it.
        """
        cache.set(
            SUMMARIES_CACHE_KEY,
            {
                "data": {key: {"cached": True} for key in PERIOD_KEYS},
                "fresh_until": time.time() + 600,
            },
            600,
        )

        with patch.object(
            contribution_summary, "PERIOD_KEYS", ["7", "30", "90", "all"]
        ), patch.object(
            contribution_summary,
            "compute_all_summaries",
            return_value={"90": {"window_days": 90}},
        ) as compute:
            data = contribution_summary.get_contribution_summary(90)

        self.assertEqual(data, {"window_days": 90})
        compute.assert_called_once()

    def test_failed_refresh_is_sent_to_sentry_once(self):
        """
        Input: Sentry set up as in the settings (Django integration, default
        ones kept), an outdated cached summary, and a refresh that raises.
        Expected: the error reaches Sentry through logger.exception, as a
        single event (no explicit capture needed).
        """

        class CapturingTransport(Transport):
            def __init__(self, options=None):
                super().__init__(options)
                self.envelopes = []

            def capture_envelope(self, envelope):
                self.envelopes.append(envelope)

        transport = CapturingTransport()
        previous_client = sentry_sdk.get_client()
        sentry_sdk.init(
            dsn="https://public@sentry.invalid/1",
            integrations=[DjangoIntegration()],
            transport=transport,
        )
        self.addCleanup(sentry_sdk.get_global_scope().set_client, previous_client)
        self.addCleanup(sentry_sdk.get_client().close)
        cache.set(
            SUMMARIES_CACHE_KEY,
            {"data": {"30": {"stale": True}}, "fresh_until": time.time() - 1},
            60,
        )

        with patch.object(
            contribution_summary,
            "compute_all_summaries",
            side_effect=DatabaseError("connection lost"),
        ):
            contribution_summary.get_contribution_summary(30)
        sentry_sdk.flush()

        events = [
            item.payload.json
            for envelope in transport.envelopes
            for item in envelope.items
            if item.type == "event"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["exception"]["values"][-1]["value"], "connection lost"
        )

    def test_summaries_returns_every_period_shortest_first(self):
        """
        Input: a contribution, then a call to the all-periods endpoint, the
        clock frozen.
        Expected: 200 with the 7-day, 30-day and whole-period summaries, in
        that order, each exactly what compute_contribution_summary returns
        for that instant.
        """
        edition(ContributorUserFactory(username="alice"), timezone.now())
        frozen = timezone.now()

        with patch.object(contribution_summary.timezone, "now", return_value=frozen):
            response = self.client.get(SUMMARIES_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "summaries": [
                    json.loads(
                        json.dumps(compute_contribution_summary(now=frozen, days=d))
                    )
                    for d in [7, 30, None]
                ]
            },
        )

    def test_summaries_and_summary_share_the_cache(self):
        """
        Input: a call to the all-periods endpoint, then one per period.
        Expected: the 3 periods are computed once in all, and each period
        endpoint returns the matching summary of the first response.
        """
        with patch.object(
            contribution_summary,
            "compute_contribution_summary",
            wraps=contribution_summary.compute_contribution_summary,
        ) as compute:
            summaries = self.client.get(SUMMARIES_URL).json()["summaries"]
            for days, summary in zip(["7", "30", "all"], summaries):
                response = self.client.get(f"{self.URL}?days={days}")
                self.assertEqual(response.json(), summary)

        self.assertEqual(compute.call_count, 3)

    def test_summaries_come_from_one_entry_while_refreshing(self):
        """
        Input: an outdated cached entry, its refresh lock held by another
        request.
        Expected: the 3 outdated summaries of that entry, served together.
        """
        outdated = {
            key: {"window_days": key, "updated_at": "outdated"} for key in PERIOD_KEYS
        }
        cache.set(
            SUMMARIES_CACHE_KEY,
            {"data": outdated, "fresh_until": time.time() - 1},
            60,
        )
        cache.add(f"{SUMMARIES_CACHE_KEY}:refreshing", True, 60)

        response = self.client.get(SUMMARIES_URL)

        self.assertEqual(
            response.json(), {"summaries": [outdated[key] for key in PERIOD_KEYS]}
        )


# Real Redis, as in production (Django's RedisCache): cache.add is an atomic
# SET NX there. Own key prefix, so that the tests only touch their own keys.
REDIS_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_CACHE_URL", "redis://redis:6379/1"),
        "KEY_PREFIX": "test_contribution_summary",
    }
}


@override_settings(CACHES=REDIS_CACHES)
class ContributionSummaryConcurrencyTest(SimpleTestCase):
    THREADS = 10
    # long enough for every thread to reach the cache, never reached when the
    # tests pass: the computations are released by the tests
    MAX_SECONDS = 10

    def setUp(self):
        self._delete_keys()
        self.addCleanup(self._delete_keys)
        self.computations = 0
        self.release = threading.Event()
        computations_lock = threading.Lock()

        def blocked_compute(now=None):
            with computations_lock:
                self.computations += 1
            self.release.wait(self.MAX_SECONDS)
            return {key: {"fresh": True} for key in PERIOD_KEYS}

        compute_patch = patch.object(
            contribution_summary, "compute_all_summaries", side_effect=blocked_compute
        )
        compute_patch.start()
        self.addCleanup(compute_patch.stop)
        self.pool = ThreadPoolExecutor(self.THREADS)
        self.addCleanup(self.pool.shutdown)
        # never leave a thread blocked, even when an assertion fails
        self.addCleanup(self.release.set)

    def _delete_keys(self):
        cache.delete_many([SUMMARIES_CACHE_KEY, f"{SUMMARIES_CACHE_KEY}:refreshing"])

    def _simultaneous_requests(self) -> list[Future]:
        """THREADS calls for the 30-day summary, started at the same time"""
        start = threading.Barrier(self.THREADS)

        def request():
            start.wait()
            return contribution_summary.get_contribution_summary(30)

        return [self.pool.submit(request) for _ in range(self.THREADS)]

    def test_empty_cache_is_computed_once(self):
        """
        Input: an empty cache (as right after the deploy), 10 simultaneous
        requests, the computation released once they all wait.
        Expected: a single computation, and every request gets its result.
        """
        requests = self._simultaneous_requests()
        # the 9 others are polling the cache meanwhile
        time.sleep(1)
        self.release.set()

        results = [r.result(timeout=self.MAX_SECONDS) for r in requests]

        self.assertEqual(self.computations, 1)
        self.assertEqual(results, [{"fresh": True}] * self.THREADS)

    def test_outdated_summary_is_computed_once_and_served_meanwhile(self):
        """
        Input: an outdated cached summary, 10 simultaneous requests, the
        computation kept blocked.
        Expected: a single computation; while it is blocked, the 9 other
        requests already got the outdated summary; once released, the request
        computing it gets the new one.
        """
        cache.set(
            SUMMARIES_CACHE_KEY,
            {"data": {"30": {"stale": True}}, "fresh_until": time.time() - 1},
            60,
        )

        requests = self._simultaneous_requests()
        done, computing = wait(
            requests, timeout=self.MAX_SECONDS, return_when=FIRST_COMPLETED
        )
        deadline = time.monotonic() + self.MAX_SECONDS
        while len(computing) > 1 and time.monotonic() < deadline:
            done, computing = wait(requests, timeout=0.1)

        self.assertEqual(self.computations, 1)
        self.assertEqual(len(computing), 1)
        self.assertEqual([r.result() for r in done], [{"stale": True}] * 9)
        self.release.set()
        self.assertEqual(
            computing.pop().result(timeout=self.MAX_SECONDS), {"fresh": True}
        )

    def test_periods_requested_together_during_a_refresh_match(self):
        """
        Input: an outdated cached entry, then the 3 periods requested at the
        same time as the site does, one call to the all-periods endpoint per
        request, while the refresh is blocked.
        Expected: each response holds 3 summaries of the same computation
        (one gets the new ones, the others the outdated ones), never a mix.
        """
        cache.set(
            SUMMARIES_CACHE_KEY,
            {
                "data": {key: {"stale": True} for key in PERIOD_KEYS},
                "fresh_until": time.time() - 1,
            },
            60,
        )
        start = threading.Barrier(3)

        def site_request():
            start.wait()
            return contribution_summary.get_all_contribution_summaries()

        requests = [self.pool.submit(site_request) for _ in range(3)]
        served, refreshing = wait(
            requests, timeout=self.MAX_SECONDS, return_when=FIRST_COMPLETED
        )
        deadline = time.monotonic() + self.MAX_SECONDS
        while len(refreshing) > 1 and time.monotonic() < deadline:
            served, refreshing = wait(requests, timeout=0.1)
        self.release.set()

        responses = [r.result(timeout=self.MAX_SECONDS) for r in requests]
        self.assertEqual(self.computations, 1)
        self.assertCountEqual(
            responses,
            [[{"fresh": True}] * 3, [{"stale": True}] * 3, [{"stale": True}] * 3],
        )
