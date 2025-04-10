from datetime import date, timedelta
from django.test import TestCase

from batid.services.kpi import get_kpi
from batid.services.kpi import get_kpi_most_recent, compute_active_buildings_count
from batid.models import KPI
from batid.models import Building


class KPICompute(TestCase):

    def setUp(self):

        # Active/inactive buildings
        Building.object.create(rnb_id="one", is_active=True)
        Building.object.create(rnb_id="two", is_active=False)

    def test_compute_active_buildings_count(self):

        value = compute_active_buildings_count()
        self.assertEqual(value, 1)


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
