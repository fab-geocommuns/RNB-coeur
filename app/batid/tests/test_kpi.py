from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.test import TestCase
from rest_framework_tracking.models import APIRequestLog

from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import Department_subdivided
from batid.models import KPI
from batid.models.report import Report
from batid.services.kpi import backfill_api_requests_kpi
from batid.services.kpi import compute_today_kpis
from batid.services.kpi import count_active_buildings
from batid.services.kpi import count_api_requests
from batid.services.kpi import count_editors
from batid.services.kpi import count_edits
from batid.services.kpi import count_edits_by_department
from batid.services.kpi import count_fixed_reports
from batid.services.kpi import count_pending_reports
from batid.services.kpi import count_real_buildings
from batid.services.kpi import count_real_buildings_wo_addresses
from batid.services.kpi import count_refused_reports
from batid.services.kpi import count_reports
from batid.services.kpi import get_kpi
from batid.services.kpi import get_kpi_most_recent
from batid.services.kpi import KPI_API_REQUESTS_COUNT


def make_api_log(requested_at):
    """Helper to create a minimal APIRequestLog at a given datetime."""
    return APIRequestLog.objects.create(
        requested_at=requested_at,
        response_ms=10,
        path="/api/alpha/buildings/",
        host="http://testserver",
        method="GET",
    )


class KPIDailyRun(TestCase):
    def setUp(self):
        compute_today_kpis()

    def test_all_are_done(self):
        """No data: only the 11 scalar KPIs should be created (0 dept KPIs)."""

        daily_kpis = [
            "active_buildings_count",
            "real_buildings_count",
            "real_buildings_wo_addresses_count",
            "building_address_links_count",
            "editors_count",
            "edits_count",
            "reports_count",
            "pending_reports_count",
            "fixed_reports_count",
            "refused_reports_count",
            "api_requests_count",
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


class CountEditsByDepartment(TestCase):
    def setUp(self):
        """
        2 contributions in dept 75, 1 in dept 69, 1 report (excluded).
        Expected: {75: 2, 69: 1}.
        """
        dept_75_polygon = GEOSGeometry(
            "POLYGON((2.0 48.0, 2.0 49.0, 3.0 49.0, 3.0 48.0, 2.0 48.0))", srid=4326
        )
        dept_69_polygon = GEOSGeometry(
            "POLYGON((4.0 45.0, 4.0 46.0, 5.0 46.0, 5.0 45.0, 4.0 45.0))", srid=4326
        )
        Department_subdivided.objects.create(
            code="75", name="Paris", shape=dept_75_polygon
        )
        Department_subdivided.objects.create(
            code="69", name="Rhône", shape=dept_69_polygon
        )

        Building.objects.create(
            rnb_id="BDG75A", point=Point(2.5, 48.5, srid=4326), is_active=True
        )
        Building.objects.create(
            rnb_id="BDG75B", point=Point(2.6, 48.6, srid=4326), is_active=True
        )
        Building.objects.create(
            rnb_id="BDG69A", point=Point(4.5, 45.5, srid=4326), is_active=True
        )

        Contribution.objects.create(rnb_id="BDG75A", report=False)
        Contribution.objects.create(rnb_id="BDG75B", report=False)
        Contribution.objects.create(rnb_id="BDG69A", report=False)
        # report=True should be excluded
        Contribution.objects.create(rnb_id="BDG75A", report=True)

    def test(self):
        result = count_edits_by_department()
        self.assertEqual(result["75"], 2)
        self.assertEqual(result["69"], 1)
        self.assertEqual(len(result), 2)


class CountApiRequests(TestCase):
    def setUp(self):
        """3 API requests in the log."""
        make_api_log(datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc))
        make_api_log(datetime(2024, 2, 5, 8, 0, tzinfo=timezone.utc))
        make_api_log(datetime(2024, 3, 20, 9, 0, tzinfo=timezone.utc))

    def test_count(self):
        """3 log entries: count_api_requests should return 3."""
        self.assertEqual(count_api_requests(), 3)

    def test_kpi_created_by_compute(self):
        """compute_today_kpis creates an api_requests_count KPI with the total count."""
        compute_today_kpis()
        kpi = KPI.objects.get(name=KPI_API_REQUESTS_COUNT, value_date=date.today())
        self.assertEqual(kpi.value, 3)


class BackfillApiRequestsKpi(TestCase):
    def setUp(self):
        """
        2 requests in Jan 2024, 1 in Feb 2024.
        Expected backfill: Jan KPI = 2, Feb KPI = 3 (cumulative).
        """
        make_api_log(datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc))
        make_api_log(datetime(2024, 1, 25, 8, 0, tzinfo=timezone.utc))
        make_api_log(datetime(2024, 2, 5, 9, 0, tzinfo=timezone.utc))

    def test_creates_one_kpi_per_month(self):
        """Backfill should create one KPI per past month, stopping before current month."""
        backfill_api_requests_kpi()
        kpis = KPI.objects.filter(name=KPI_API_REQUESTS_COUNT).order_by("value_date")
        # Should not include current month
        for kpi in kpis:
            self.assertLess(kpi.value_date, date.today().replace(day=1))

    def test_cumulative_values(self):
        """Jan KPI = 2 (requests up to Jan 31), Feb KPI = 3 (cumulative up to Feb 29)."""
        backfill_api_requests_kpi()
        jan_kpi = KPI.objects.get(
            name=KPI_API_REQUESTS_COUNT, value_date=date(2024, 1, 31)
        )
        feb_kpi = KPI.objects.get(
            name=KPI_API_REQUESTS_COUNT, value_date=date(2024, 2, 29)
        )
        self.assertEqual(jan_kpi.value, 2)
        self.assertEqual(feb_kpi.value, 3)

    def test_idempotent(self):
        """Calling backfill twice should not create duplicate entries."""
        backfill_api_requests_kpi()
        first_count = KPI.objects.filter(name=KPI_API_REQUESTS_COUNT).count()
        backfill_api_requests_kpi()
        second_count = KPI.objects.filter(name=KPI_API_REQUESTS_COUNT).count()

        self.assertEqual(second_count, first_count)

    def test_empty_log(self):
        """Empty APIRequestLog: backfill should create no KPIs."""
        APIRequestLog.objects.all().delete()
        backfill_api_requests_kpi()
        self.assertEqual(KPI.objects.filter(name=KPI_API_REQUESTS_COUNT).count(), 0)
