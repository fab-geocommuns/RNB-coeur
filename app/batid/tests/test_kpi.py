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
from batid.services.kpi import compute_today_kpis
from batid.services.kpi import count_active_buildings
from batid.services.kpi import count_editors
from batid.services.kpi import count_edits
from batid.services.kpi import count_fixed_reports
from batid.services.kpi import count_pending_reports
from batid.services.kpi import count_real_buildings
from batid.services.kpi import count_real_buildings_wo_addresses
from batid.services.kpi import count_refused_reports
from batid.services.kpi import count_reports
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
