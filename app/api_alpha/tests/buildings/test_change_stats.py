from datetime import date, timedelta

from batid.models import KPI
from rest_framework.test import APITestCase


class BuildingChangeStatsTest(APITestCase):
    def test_missing_since_returns_400(self):
        response = self.client.get(
            "/api/alpha/buildings/change_stats/?until=2024-01-15"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("since", response.json().get("detail", ""))

    def test_missing_until_returns_400(self):
        response = self.client.get(
            "/api/alpha/buildings/change_stats/?since=2024-01-01"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("until", response.json().get("detail", ""))

    def test_invalid_date_format_returns_400(self):
        response = self.client.get(
            "/api/alpha/buildings/change_stats/?since=01-01-2024&until=2024-01-15"
        )
        self.assertEqual(response.status_code, 400)

    def test_since_after_until_returns_400(self):
        response = self.client.get(
            "/api/alpha/buildings/change_stats/?since=2024-01-15&until=2024-01-01"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("since", response.json().get("detail", ""))

    def test_since_before_2024_returns_400(self):
        """since antérieur au 2024-01-01 doit retourner 400."""
        response = self.client.get(
            "/api/alpha/buildings/change_stats/?since=2023-06-01&until=2024-01-15"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("2024-01-01", response.json().get("detail", ""))

    def test_returns_list_with_correct_structure(self):
        since = (date.today() - timedelta(days=1)).isoformat()
        until = date.today().isoformat()
        response = self.client.get(
            f"/api/alpha/buildings/change_stats/?since={since}&until={until}"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        zero_events = {"import_bdtopo": 0, "import_bal": 0, "contributions": 0}
        expected_first = {"date": since, "events_count": zero_events}
        expected_second = {"date": until, "events_count": zero_events}
        self.assertDictEqual(data[0], expected_first)
        self.assertDictEqual(data[1], expected_second)

    def test_returns_stored_kpi_values(self):
        since = date.today() - timedelta(days=1)
        until = date.today()
        KPI.objects.create(
            name="building_changes_import_bdtopo",
            value=7,
            value_date=since,
        )
        KPI.objects.create(
            name="building_changes_import_bal",
            value=3,
            value_date=since,
        )
        KPI.objects.create(
            name="building_changes_contributions",
            value=1,
            value_date=since,
        )
        response = self.client.get(
            f"/api/alpha/buildings/change_stats/?since={since.isoformat()}&until={until.isoformat()}"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        first = data[0]
        self.assertEqual(first["date"], since.isoformat())
        self.assertEqual(first["events_count"]["import_bdtopo"], 7)
        self.assertEqual(first["events_count"]["import_bal"], 3)
        self.assertEqual(first["events_count"]["contributions"], 1)
