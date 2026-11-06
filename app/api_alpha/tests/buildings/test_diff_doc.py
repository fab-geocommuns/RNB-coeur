"""
Tests checking that the documentation of GET /buildings/diff/ matches the CSV the
endpoint really produces: they fail when the diff changes and its doc is not updated.
"""

import csv
import inspect
import io
import re

from api_alpha.endpoints.buildings.get_diff import _build_copy_query
from api_alpha.utils.rnb_doc import build_schema_all_endpoints
from batid.models import Building
from batid.models.building import EventType
from django.contrib.gis.geos import GEOSGeometry
from django.test import SimpleTestCase, TransactionTestCase
from django.utils.http import urlencode


def _diff_doc() -> dict:
    return build_schema_all_endpoints()["paths"]["/api/alpha/buildings/diff/"]["get"]


def _documented_header() -> list[str]:
    example = _diff_doc()["responses"]["200"]["content"]["text/csv"]["example"]
    return example.split(",")


class DiffDocDescriptionTest(SimpleTestCase):
    def test_every_event_type_is_documented(self):
        """
        Input: every value of the EventType enum.
        Expected: each value appears in the list mapping event_type to action.
        """
        description = _diff_doc()["description"]
        for event_type in EventType.values():
            with self.subTest(event_type=event_type):
                self.assertIn(f"<li>`{event_type}` (", description)

    def test_every_action_is_documented(self):
        """
        Input: the action values written by the SQL query of the diff (THEN '...').
        Expected: the description announces that number of actions and names each of
        them.
        """
        source = inspect.getsource(_build_copy_query)
        actions = sorted(set(re.findall(r"THEN '(\w+)'", source)))
        self.assertTrue(actions)

        description = _diff_doc()["description"]
        self.assertIn(f"Il existe {len(actions)} actions", description)
        for action in actions:
            with self.subTest(action=action):
                self.assertIn(f"`{action}`", description)

    def test_every_documented_column_is_described(self):
        """
        Input: the columns of the documented CSV header.
        Expected: each column has its own entry in the "Format des colonnes" list.
        """
        description = _diff_doc()["description"]
        for column in _documented_header():
            with self.subTest(column=column):
                self.assertRegex(description, rf"<li>(`\w+` et )?`{column}`")


class DiffDocMatchesCSVTest(TransactionTestCase):
    def setUp(self):
        # the diff needs at least one modification to produce a CSV
        geom = GEOSGeometry("POINT(2.35 48.85)", srid=4326)
        Building.objects.create(
            rnb_id="DOCDOCDOCDOC",
            shape=geom,
            point=geom,
            status="constructed",
            event_type="creation",
        )

    def test_since_example_is_accepted_and_header_is_documented(self):
        """
        Input: GET /buildings/diff/ with the example of the documented `since`
        parameter.
        Expected: a 200, and the CSV header is exactly the documented example header.
        """
        since = next(p for p in _diff_doc()["parameters"] if p["name"] == "since")
        r = self.client.get(
            f"/api/alpha/buildings/diff/?{urlencode({'since': since['example']})}"
        )
        self.assertEqual(r.status_code, 200)

        content = b"".join(r.streaming_content).decode("utf-8")
        header = next(csv.reader(io.StringIO(content)))
        self.assertEqual(header, _documented_header())
