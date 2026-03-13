from datetime import date
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import TestCase

from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import KPI
from batid.models.report import Report
from batid.models import BuildingImport
from batid.services.kpi import compute_today_kpis
from batid.services.kpi import count_active_buildings
from batid.services.kpi import count_building_changes_contributions
from batid.services.kpi import count_building_changes_import_bal
from batid.services.kpi import count_building_changes_import_bdtopo
from batid.services.kpi import count_editors
from batid.services.kpi import count_edits
from batid.services.kpi import count_fixed_reports
from batid.services.kpi import count_pending_reports
from batid.services.kpi import count_real_buildings
from batid.services.kpi import count_real_buildings_wo_addresses
from batid.services.kpi import count_refused_reports
from batid.services.kpi import count_reports
from batid.services.kpi import get_building_change_stats
from batid.services.kpi import get_kpi
from batid.services.kpi import get_kpi_most_recent


class KPIDailyRun(TestCase):
    def setUp(self):
        compute_today_kpis()

    def test_all_are_done(self):

        daily_kpis = [
            "active_buildings_count",
            "real_buildings_count",
            "real_buildings_wo_addresses_count",
            "editors_count",
            "edits_count",
            "reports_count",
            "pending_reports_count",
            "fixed_reports_count",
            "refused_reports_count",
            "building_changes_import_bdtopo",
            "building_changes_import_bal",
            "building_changes_contributions",
        ]

        kpis = KPI.objects.all()
        self.assertEqual(len(kpis), len(daily_kpis))

        for kpi in kpis:
            self.assertIn(kpi.name, daily_kpis)
            self.assertEqual(kpi.value_date, date.today())


class CountActiveBuildings(TestCase):
    def setUp(self):

        Building.objects.create(rnb_id="one", status="constructed", is_active=True)
        Building.objects.create(rnb_id="two", status="demolished", is_active=True)

        Building.objects.create(rnb_id="three", status="constructed", is_active=False)

    def test(self):
        value = count_active_buildings()
        self.assertEqual(value, 2)


class CountRealBuildings(TestCase):
    def setUp(self):

        # Real buildings
        Building.objects.create(rnb_id="1", status="constructed", is_active=True)
        Building.objects.create(rnb_id="2", status="notUsable", is_active=True)

        # Not real buildings
        Building.objects.create(rnb_id="3", status="constructed", is_active=False)
        Building.objects.create(rnb_id="4", status="demolished", is_active=True)

    def test(self):

        value = count_real_buildings()
        self.assertEqual(value, 2)


class CountContributions(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.u1 = None
        self.u2 = None
        self.u3 = None

    def setUp(self):

        self.u1 = User.objects.create(username="u1", email="u1@u1")
        self.u2 = User.objects.create(username="u2", email="u2@u2")
        self.u3 = User.objects.create(username="u3", email="u3@u3")

        # Reports
        Report.objects.create(status="pending", point=Point(0, 0))
        Report.objects.create(status="fixed", point=Point(0, 0))
        Report.objects.create(status="rejected", point=Point(0, 0))
        Report.objects.create(status="rejected", point=Point(0, 0))
        Report.objects.create(status="rejected", point=Point(0, 0))

        # Edits
        Contribution.objects.create(report=False, status="fixed", review_user=self.u1)
        Contribution.objects.create(report=False, status="fixed", review_user=self.u1)
        Contribution.objects.create(report=False, status="fixed", review_user=self.u2)

    def test_count(self):
        # Test reports
        self.assertEqual(count_reports(), 5)
        self.assertEqual(count_pending_reports(), 1)
        self.assertEqual(count_fixed_reports(), 1)
        self.assertEqual(count_refused_reports(), 3)

        # Test edits
        self.assertEqual(count_editors(), 2)
        self.assertEqual(count_edits(), 3)


class CountRealBuildingsWithoutAddress(TestCase):
    def setUp(self):

        # Addresses
        Address.objects.create(id="one")
        Address.objects.create(id="two")
        Address.objects.create(id="three")

        # Real buildings
        Building.objects.create(
            rnb_id="r1", status="constructed", addresses_id=["one", "two"]
        )
        # test empty array
        Building.objects.create(rnb_id="r2", status="notUsable", addresses_id=[])
        # test None
        Building.objects.create(rnb_id="r3", status="notUsable", addresses_id=None)

        # Not real buildings
        Building.objects.create(
            rnb_id="3", status="constructed", is_active=False, addresses_id=["one"]
        )
        Building.objects.create(rnb_id="4", status="demolished", is_active=True)

    def test(self):

        value = count_real_buildings_wo_addresses()
        self.assertEqual(value, 2)


class TestKPI(TestCase):
    def setUp(self):

        # Create a yesterday KPI
        yesterday = date.today() - timedelta(days=1)
        KPI.objects.create(name="dummy", value=1, value_date=yesterday)
        # Create a today KPI
        KPI.objects.create(name="dummy", value=2, value_date=date.today())
        # Crate a month ago KPI
        month_ago = date.today() - timedelta(days=30)
        KPI.objects.create(name="dummy", value=3, value_date=month_ago)

    def test_order(self):

        # Get the most recent KPI
        kpi = get_kpi_most_recent("dummy")
        self.assertEqual(kpi.value, 2)
        self.assertEqual(kpi.value_date, date.today())

        # get the whole period
        kpis = get_kpi("dummy")
        self.assertEqual(len(kpis), 3)

        self.assertEqual(kpis[0].value, 3)
        self.assertEqual(kpis[0].value_date, date.today() - timedelta(days=30))

        self.assertEqual(kpis[1].value, 1)
        self.assertEqual(kpis[1].value_date, date.today() - timedelta(days=1))

        self.assertEqual(kpis[2].value, 2)
        self.assertEqual(kpis[2].value_date, date.today())

    def test_since(self):

        yesterday = date.today() - timedelta(days=1)
        kpis = get_kpi("dummy", since=yesterday)

        self.assertEqual(len(kpis), 2)

        self.assertEqual(kpis[0].value, 1)
        self.assertEqual(kpis[0].value_date, date.today() - timedelta(days=1))

        self.assertEqual(kpis[1].value, 2)
        self.assertEqual(kpis[1].value_date, date.today())

    def test_until(self):

        yesterday = date.today() - timedelta(days=1)
        kpis = get_kpi("dummy", until=yesterday)

        self.assertEqual(len(kpis), 2)

        self.assertEqual(kpis[0].value, 3)
        self.assertEqual(kpis[0].value_date, date.today() - timedelta(days=30))

        self.assertEqual(kpis[1].value, 1)
        self.assertEqual(kpis[1].value_date, date.today() - timedelta(days=1))

    def test_since_until(self):

        yesterday = date.today() - timedelta(days=1)
        kpis = get_kpi("dummy", since=yesterday, until=yesterday)

        self.assertEqual(len(kpis), 1)

        self.assertEqual(kpis[0].value, 1)
        self.assertEqual(kpis[0].value_date, date.today() - timedelta(days=1))

    def test_name_date_uniqueness(self):

        # creating a new KPI with the same name and date should raise an error
        yesterday = date.today() - timedelta(days=1)
        with self.assertRaises(Exception):
            KPI.objects.create(name="dummy", value=4, value_date=yesterday)


class CountBuildingChangesImportBdtopo(TestCase):
    def setUp(self):
        self.building_import = BuildingImport.objects.create(
            import_source="bdtopo",
            building_created_count=0,
            building_updated_count=0,
        )
        Building.objects.create(
            rnb_id="BDGBDTOPO01",
            status="constructed",
            event_origin={"source": "import", "id": self.building_import.id},
        )

    def test(self):
        self.assertEqual(count_building_changes_import_bdtopo(date.today()), 1)

    def test_ignores_other_sources(self):
        bal_import = BuildingImport.objects.create(
            import_source="bal",
            building_created_count=0,
            building_updated_count=0,
        )
        Building.objects.create(
            rnb_id="BDGBAL00002",
            status="constructed",
            event_origin={"source": "import", "id": bal_import.id},
        )
        self.assertEqual(count_building_changes_import_bdtopo(date.today()), 1)

    def test_empty_returns_zero(self):
        """Date sans aucun event bdtopo : compte 0."""
        self.assertEqual(count_building_changes_import_bdtopo(date(2000, 1, 1)), 0)


class CountBuildingChangesImportBal(TestCase):
    def setUp(self):
        self.building_import = BuildingImport.objects.create(
            import_source="bal",
            building_created_count=0,
            building_updated_count=0,
        )
        Building.objects.create(
            rnb_id="BDGBAL00001",
            status="constructed",
            event_origin={"source": "import", "id": self.building_import.id},
        )

        Building.objects.create(
            rnb_id="BDGBAL00002",
            status="constructed",
            event_origin={"source": "import", "id": self.building_import.id},
        )
        Building.objects.create(
            rnb_id="BDGBAL00003",
            status="constructed",
            event_origin={"source": "import", "id": self.building_import.id},
        )

    def test(self):
        self.assertEqual(count_building_changes_import_bal(date.today()), 3)

    def test_empty_returns_zero(self):
        """Date sans aucun event bal : compte 0."""
        self.assertEqual(count_building_changes_import_bal(date(2000, 1, 1)), 0)


class CountBuildingChangesContributions(TestCase):
    def setUp(self):
        Building.objects.create(
            rnb_id="BDGCONTRIB01",
            status="constructed",
            event_origin={"source": "contribution"},
        )

    def test(self):
        self.assertGreaterEqual(count_building_changes_contributions(date.today()), 1)

    def test_empty_returns_zero(self):
        self.assertEqual(count_building_changes_contributions(date(2000, 1, 1)), 0)


class GetBuildingChangeStats(TestCase):
    def test_returns_one_entry_per_day_with_zeros_when_no_kpis(self):
        since = date.today() - timedelta(days=2)
        until = date.today()
        result = get_building_change_stats(since=since, until=until)
        self.assertEqual(len(result), 3)
        for item in result:
            self.assertIn("date", item)
            self.assertIn("events_count", item)
            self.assertEqual(
                item["events_count"],
                {"import_bdtopo": 0, "import_bal": 0, "contributions": 0},
            )

    def test_single_day_returns_one_entry(self):
        """Plage d'un seul jour (since == until) : une entrée."""
        d = date(2024, 6, 15)
        result = get_building_change_stats(since=d, until=d)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["date"], "2024-06-15")
        self.assertEqual(
            result[0]["events_count"],
            {"import_bdtopo": 0, "import_bal": 0, "contributions": 0},
        )

    def test_returns_stored_kpi_values(self):
        since = date.today() - timedelta(days=1)
        until = date.today()
        KPI.objects.create(
            name="building_changes_import_bdtopo",
            value=10,
            value_date=since,
        )
        KPI.objects.create(
            name="building_changes_import_bal",
            value=5,
            value_date=since,
        )
        KPI.objects.create(
            name="building_changes_contributions",
            value=2,
            value_date=since,
        )
        result = get_building_change_stats(since=since, until=until)
        self.assertEqual(len(result), 2)
        first = result[0]
        self.assertEqual(first["date"], since.isoformat())
        self.assertEqual(first["events_count"]["import_bdtopo"], 10)
        self.assertEqual(first["events_count"]["import_bal"], 5)
        self.assertEqual(first["events_count"]["contributions"], 2)
        second = result[1]
        self.assertEqual(second["date"], until.isoformat())
        self.assertEqual(second["events_count"]["import_bdtopo"], 0)
        self.assertEqual(second["events_count"]["import_bal"], 0)
        self.assertEqual(second["events_count"]["contributions"], 0)

    def test_month_with_kpis_only_first_two_days_and_last_day(self):
        """
        Plage d'un mois (janv. 2024) : KPI uniquement pour le 1er, 2e et 31e jour.
        Attendu : 31 entrées, valeurs correctes pour ces 3 jours, 0 pour les jours 3 à 30.
        """
        since = date(2024, 1, 1)
        until = date(2024, 1, 31)
        # 1er janvier
        KPI.objects.create(
            name="building_changes_import_bdtopo", value=10, value_date=since
        )
        KPI.objects.create(
            name="building_changes_import_bal", value=2, value_date=since
        )
        KPI.objects.create(
            name="building_changes_contributions", value=1, value_date=since
        )
        # 2 janvier
        day2 = date(2024, 1, 2)
        KPI.objects.create(
            name="building_changes_import_bdtopo", value=5, value_date=day2
        )
        KPI.objects.create(
            name="building_changes_import_bal", value=0, value_date=day2
        )
        KPI.objects.create(
            name="building_changes_contributions", value=0, value_date=day2
        )
        # 31 janvier (pas de KPI pour les jours 3 à 30)
        day31 = date(2024, 1, 31)
        KPI.objects.create(
            name="building_changes_import_bdtopo", value=0, value_date=day31
        )
        KPI.objects.create(
            name="building_changes_import_bal", value=3, value_date=day31
        )
        KPI.objects.create(
            name="building_changes_contributions", value=2, value_date=day31
        )

        result = get_building_change_stats(since=since, until=until)

        self.assertEqual(len(result), 31)
        # 1er jour
        self.assertEqual(result[0]["date"], "2024-01-01")
        self.assertEqual(result[0]["events_count"]["import_bdtopo"], 10)
        self.assertEqual(result[0]["events_count"]["import_bal"], 2)
        self.assertEqual(result[0]["events_count"]["contributions"], 1)
        # 2e jour
        self.assertEqual(result[1]["date"], "2024-01-02")
        self.assertEqual(result[1]["events_count"]["import_bdtopo"], 5)
        self.assertEqual(result[1]["events_count"]["import_bal"], 0)
        self.assertEqual(result[1]["events_count"]["contributions"], 0)
        # Jours 3 à 30 : tout à 0
        zero_events = {"import_bdtopo": 0, "import_bal": 0, "contributions": 0}
        for i in range(2, 30):
            self.assertEqual(result[i]["events_count"], zero_events)
        # 31e jour
        self.assertEqual(result[30]["date"], "2024-01-31")
        self.assertEqual(result[30]["events_count"]["import_bdtopo"], 0)
        self.assertEqual(result[30]["events_count"]["import_bal"], 3)
        self.assertEqual(result[30]["events_count"]["contributions"], 2)
